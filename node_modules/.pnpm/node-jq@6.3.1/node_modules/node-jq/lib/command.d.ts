import { type FilterInput, type JsonInput, type OptionsInput } from './options';
interface Command {
    command: string;
    args: string[];
    stdin: string;
}
export declare const commandFactory: (filter: FilterInput, json: JsonInput, options?: OptionsInput) => Command;
export {};
