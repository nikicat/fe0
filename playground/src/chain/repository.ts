import { config } from "../config";
import { Repository } from "../domain/repository";

// The repository that config.ts records.
export const repository = new Repository(config.repo, config.messages);
