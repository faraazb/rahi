import initSqlJs, { type Database, type SqlJsStatic } from 'sql.js';
import wasmUrl from 'sql.js/dist/sql-wasm-browser.wasm?url';

let engine: Promise<SqlJsStatic> | undefined;

export function sqlEngine(): Promise<SqlJsStatic> {
	engine ??= initSqlJs({ locateFile: () => wasmUrl });
	return engine;
}

export async function openDatabase(bytes: Uint8Array): Promise<Database> {
	const SQL = await sqlEngine();
	return new SQL.Database(bytes);
}

/** Rows of a query as plain objects. */
export function all<T>(db: Database, sql: string, params: (string | number | null)[] = []): T[] {
	const stmt = db.prepare(sql);
	try {
		stmt.bind(params);
		const out: T[] = [];
		while (stmt.step()) out.push(stmt.getAsObject() as T);
		return out;
	} finally {
		stmt.free();
	}
}

export function one<T>(db: Database, sql: string, params: (string | number | null)[] = []): T | null {
	return all<T>(db, sql, params)[0] ?? null;
}
