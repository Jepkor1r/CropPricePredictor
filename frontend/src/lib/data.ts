import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";
import { cache } from "react";

import type { Dashboard, History } from "./types";

const DATA_DIR = path.join(process.cwd(), "public", "data");

/** Deduped per request by React.cache; the JSON is a build artifact of the
 *  Python pipeline (scripts/export_frontend_data.py). */
export const getDashboard = cache(async (): Promise<Dashboard> => {
  const raw = await readFile(path.join(DATA_DIR, "dashboard.json"), "utf8");
  return JSON.parse(raw) as Dashboard;
});

export const getHistory = cache(async (): Promise<History> => {
  const raw = await readFile(path.join(DATA_DIR, "history.json"), "utf8");
  return JSON.parse(raw) as History;
});
