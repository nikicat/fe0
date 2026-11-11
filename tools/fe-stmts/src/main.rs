//! Prints where Fe's parser puts the statements of each block of a Fe source.
//!
//! usage: fe-stmts FILE
//!
//! Each line is one block: the byte offset of its `{`, then the byte range `start-end` of each
//! statement, without the newlines and comments around it. tools/newline_check.py compares the
//! output with Fe0's newline rule (SPEC.md §3.4). Errors when Fe cannot parse FILE.

use std::{env, fs, process::ExitCode};

use fe_parser::{RecoveryMode, SyntaxKind, SyntaxNode, TextRange, ast::BlockExpr, parse_source_file};
use rowan::ast::AstNode;

fn main() -> ExitCode {
    let Some(path) = env::args().nth(1) else {
        eprintln!("usage: fe-stmts FILE");
        return ExitCode::FAILURE;
    };
    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(e) => {
            eprintln!("{path}: {e}");
            return ExitCode::FAILURE;
        }
    };
    let (green, errors) = parse_source_file(&text, RecoveryMode::NoRecover);
    if let Some(error) = errors.first() {
        eprintln!("{path}: Fe does not parse it: {error:?}");
        return ExitCode::FAILURE;
    }
    let root = SyntaxNode::new_root(green);
    for block in root.descendants().filter_map(BlockExpr::cast) {
        let open = u32::from(block.syntax().text_range().start());
        let stmts: Vec<String> = block
            .stmts()
            .filter_map(|stmt| code_range(stmt.syntax()))
            .map(|r| format!("{}-{}", u32::from(r.start()), u32::from(r.end())))
            .collect();
        println!("{open} {}", stmts.join(" "));
    }
    ExitCode::SUCCESS
}

/// The range of `node` from its first token to its last that is neither a newline, white space
/// nor a comment.
fn code_range(node: &SyntaxNode) -> Option<TextRange> {
    let code = |t: &fe_parser::SyntaxToken| {
        !matches!(t.kind(), SyntaxKind::Newline | SyntaxKind::WhiteSpace | SyntaxKind::Comment)
    };
    let tokens: Vec<_> = node.descendants_with_tokens().filter_map(|e| e.into_token()).filter(code).collect();
    Some(TextRange::new(tokens.first()?.text_range().start(), tokens.last()?.text_range().end()))
}
