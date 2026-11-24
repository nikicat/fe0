// The typed client of Registry (registry/README.md), from its committed interface.
import {
  type Address, type GetEventArgs, type Hex, type Log, type PublicClient, decodeFunctionResult,
  encodeFunctionData, getContract, hexToBigInt, isAddressEqual, numberToHex, parseEventLogs,
} from "viem";
import { config, registryAbi } from "../config";
import type { EncodedArgs } from "../domain/abi";
import { type BlockRange, blockRanges } from "../domain/blocks";
import type { Deployed } from "../domain/config";
import { CreateX, type Creation } from "../domain/createx";
import { groupByValue, maxOf, memoize, memoizeSync, minOf } from "../domain/generic";
import type { ListCursor, ListPage } from "../domain/registryList";
import type { Salt } from "../domain/salt";
import { firstAtLeast } from "../domain/search";
import { Program, type Source } from "../domain/source";
import { publicClient } from "./chains";
import { Compiler } from "./compiler";
import { repository } from "./repository";
import { revertData } from "./revertData";
import { type Mined, type Progress, type Tx, transact } from "./transact";

// How far past the first block of the last recorded Ethereum block the event read goes on
// Arbitrum. An Ethereum block takes about 12 s and Arbitrum makes about 4 blocks a second, so
// one Ethereum block spans about 50 Arbitrum blocks, and 10,000 is a wide margin over that.
const L1_BLOCK_SPAN = 10_000n;
// The Ethereum block of a header without `l1BlockNumber`: past every block that a record names.
const NO_L1_BLOCK = 1n << 64n;

// The block number that `block.number` gave when Registry recorded a contract: Ethereum's on a
// chain whose `l1Blocks` is true, and this chain's otherwise
// (docs/adr/0031-deployment-registry.md, "Reading").
type RecordedBlock = bigint & { readonly __brand: "RecordedBlock" };

// The `Registered` events to look for: those of `addresses` in the blocks of `range`.
interface EventQuery {
  addresses: Address[];
  range: BlockRange;
}

// What Registry recorded of a contract (docs/adr/0031-deployment-registry.md, "Where each fact
// is kept").
export interface Recorded {
  compiler: Address;
  salt: Salt;
  source: Source;
  args: EncodedArgs;
  // The block of this chain that holds the `Registered` event.
  block: bigint;
}

// The contract that a `deploy` reached, and the record that the `deploy` made of it, or null
// when Registry had recorded it before.
export interface Reached {
  address: Address;
  created: boolean;
  mined: Mined;
  record: Recorded | null;
}

// One deployment's Registry, which deploys programs and records each with its source
// (docs/adr/0031-deployment-registry.md).
export class Registry {
  readonly #deployment: Deployed;
  readonly #client: PublicClient;
  readonly #contract;

  // Returns the Registry of `deployment`. Each deployment has one, which serves every read, so
  // that it reads each block header once.
  static readonly of = memoizeSync((deployment: Deployed) => new Registry(deployment));

  private constructor(deployment: Deployed) {
    this.#deployment = deployment;
    this.#client = publicClient(deployment);
    this.#contract = getContract({
      address: deployment.registry.address, abi: registryAbi, client: this.#client,
    });
  }

  // Deploys `creation` through Registry from the wallet, with the deployment's Compiler, and
  // reports each step to `progress`. Errors as `transact` does, or with the init code's revert
  // data when CreateX creates no contract.
  async deploy(creation: Creation, progress: (p: Progress) => void): Promise<Reached> {
    let sent;
    try {
      sent = await transact(this.#deployment, this.#deployTx(creation), progress);
    } catch (e) {
      await this.#explainCreation(e, creation);
      throw e;
    }
    const { addr, created } = decodeFunctionResult({
      abi: registryAbi, functionName: "deploy", data: sent.result,
    });
    return {
      address: addr, created, mined: sent.mined, record: this.#registered(sent.logs, addr),
    };
  }

  // Returns the transaction that deploys `creation` through Registry.
  #deployTx({ program, args, salt }: Creation): Tx {
    return {
      to: this.#deployment.registry.address,
      data: encodeFunctionData({
        abi: registryAbi, functionName: "deploy",
        args: [this.#deployment.compiler.address, salt, program.bytes(), args],
      }),
    };
  }

  // Errors as `#runInitCode` does when `e` reverts because CreateX created no contract.
  async #explainCreation(e: unknown, creation: Creation): Promise<void> {
    const data = revertData(e);
    if (data !== null && repository.decodeRevert(data).kind === "creation") {
      await this.#runInitCode(creation);
    }
  }

  // Runs the init code of `creation` by `eth_call`, for the revert data that CreateX does not
  // pass on (docs/adr/0031-deployment-registry.md, "Deploying"). Errors with viem's error,
  // which carries that data, when the init code reverts.
  async #runInitCode(creation: Creation): Promise<void> {
    const code = await new Compiler(this.#deployment).compile(creation.program);
    await this.#client.call({ data: creation.initCode(code) });
  }

  // Returns the record of `addr` from the `Registered` event of this Registry in `logs`, or
  // null when there is none.
  #registered(logs: Log[], addr: Address): Recorded | null {
    const event = parseEventLogs({ abi: registryAbi, eventName: "Registered", logs })
      .find((e) => isAddressEqual(e.address, this.#deployment.registry.address)
        && isAddressEqual(e.args.addr, addr));
    return event === undefined ? null : recordOf(event.args, event.blockNumber);
  }

  async page(cursor: ListCursor): Promise<ListPage> {
    const { account } = cursor;
    const read = (start: bigint, n: bigint) => account === null
      ? this.#contract.read.contracts([start, n])
      : this.#contract.read.contractsOf([account, start, n]);
    const { total } = await read(0n, 0n);
    const { start, count } = cursor.window(total);
    const { items } = await read(start, count);
    return cursor.page(total, items);
  }

  // Returns what Registry recorded of each of `addresses`, with null for one whose record it
  // did not find (docs/adr/0031-deployment-registry.md, "Reading"). The addresses are
  // checksummed (EIP-55), as the route gives them.
  async records(addresses: readonly Address[]): Promise<Map<Address, Recorded | null>> {
    const blocks = await this.#registeredBlocks(addresses);
    const queries = await this.#eventQueries(blocks);
    const found = await Promise.all(queries.map((q) => this.#readEvents(q)));
    const records = new Map(found.flatMap((m) => [...m]));
    return new Map(addresses.map((a) => [a, records.get(a) ?? null]));
  }

  // Returns the block that Registry recorded for each of `addresses` that it recorded.
  async #registeredBlocks(addresses: readonly Address[]): Promise<Map<Address, RecordedBlock>> {
    const blocks = await Promise.all(addresses.map(async (addr) => {
      const { registered_block: block } = await this.#contract.read.info([addr]);
      return [addr, block as RecordedBlock] as const;
    }));
    return new Map(blocks.filter(([, block]) => block !== 0n));
  }

  // Returns the event queries that find the records of `blocks`: each block itself, or on a
  // chain whose `l1Blocks` is true, the blocks that the headers place in those Ethereum blocks
  // (docs/adr/0031-deployment-registry.md, "Reading").
  async #eventQueries(blocks: Map<Address, RecordedBlock>): Promise<EventQuery[]> {
    if (!this.#deployment.chain.l1Blocks) {
      return [...groupByValue(blocks)].map(([block, addresses]) =>
        ({ addresses, range: { from: block, to: block } }));
    }
    const [first, ...rest] = blocks.values();
    if (first === undefined) return [];
    const range = await this.#l1Range(minOf(first, ...rest), maxOf(first, ...rest));
    return [{ addresses: [...blocks.keys()], range }];
  }

  // Returns the blocks of this chain from the first one of the Ethereum block `l1First` to
  // L1_BLOCK_SPAN past the first one of `l1Last`.
  async #l1Range(l1First: RecordedBlock, l1Last: RecordedBlock): Promise<BlockRange> {
    const latest = await this.#client.getBlockNumber();
    const from = await firstAtLeast({ from: 0n, end: latest + 1n }, l1First, this.#l1Block);
    const last = await firstAtLeast({ from, end: latest + 1n }, l1Last, this.#l1Block);
    return { from, to: minOf(last + L1_BLOCK_SPAN, latest) };
  }

  // Returns the Ethereum block of the block `n` of this chain, from its header, or NO_L1_BLOCK
  // for a header without one.
  readonly #l1Block = memoize(async (n: bigint): Promise<bigint> => {
    const header = await this.#client.request({
      method: "eth_getBlockByNumber", params: [numberToHex(n), false],
    });
    const field = (header as { l1BlockNumber?: Hex } | null)?.l1BlockNumber;
    return field === undefined ? NO_L1_BLOCK : hexToBigInt(field);
  });

  // Returns the record of each address of `query` whose `Registered` event it finds.
  async #readEvents({ addresses, range }: EventQuery): Promise<Map<Address, Recorded>> {
    const found = new Map<Address, Recorded>();
    const size = BigInt(this.#deployment.chain.logRange);
    for (const { from, to } of blockRanges(range, size)) {
      const events = await this.#client.getContractEvents({
        address: this.#deployment.registry.address, abi: registryAbi, eventName: "Registered",
        args: { addr: addresses }, fromBlock: from, toBlock: to, strict: true,
      });
      for (const { args, blockNumber } of events) {
        found.set(args.addr, recordOf(args, blockNumber));
      }
    }
    return found;
  }
}

// The CreateX of every deployment (Config.createx).
export const createx = new CreateX(config.createx);

// Returns the record that a `Registered` event with `args` in the block `block` holds.
const recordOf = (
  { compiler, salt, src, args }: GetEventArgs<typeof registryAbi, "Registered",
    { EnableUnion: false; IndexedOnly: false; Required: true }>,
  block: bigint,
): Recorded =>
  ({
    compiler, salt: salt as Salt, args: args as EncodedArgs,
    source: Program.fromBytes(src).source, block,
  });
