import type { FilterInput, JsonInput, OptionsInput } from './options';
export declare const run: (filter: FilterInput, json: JsonInput, options?: OptionsInput, cwd?: string, detached?: boolean) => Promise<object | string | undefined>;
