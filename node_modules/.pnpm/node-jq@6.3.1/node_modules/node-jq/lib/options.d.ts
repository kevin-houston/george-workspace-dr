import * as z from 'zod';
declare const literalSchema: z.ZodUnion<[z.ZodString, z.ZodNumber, z.ZodBoolean, z.ZodNull]>;
type Literal = z.infer<typeof literalSchema>;
export type Json = Literal | {
    [key: string]: Json;
} | Json[];
export declare const jsonTypeSchema: z.ZodType<Json>;
export declare const optionsSchema: z.ZodObject<{
    args: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodType<Json, z.ZodTypeDef, Json>>>;
    color: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    input: z.ZodDefault<z.ZodOptional<z.ZodEnum<["file", "json", "string"]>>>;
    output: z.ZodDefault<z.ZodOptional<z.ZodEnum<["pretty", "compact", "string", "json"]>>>;
    raw: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    slurp: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    sort: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
}, "strip", z.ZodTypeAny, {
    sort: boolean;
    color: boolean;
    input: "string" | "file" | "json";
    output: "string" | "json" | "pretty" | "compact";
    raw: boolean;
    slurp: boolean;
    args?: Record<string, Json> | undefined;
}, {
    sort?: boolean | undefined;
    args?: Record<string, Json> | undefined;
    color?: boolean | undefined;
    input?: "string" | "file" | "json" | undefined;
    output?: "string" | "json" | "pretty" | "compact" | undefined;
    raw?: boolean | undefined;
    slurp?: boolean | undefined;
}>;
export type OptionsInput = z.input<typeof optionsSchema>;
export type OptionsOutput = z.output<typeof optionsSchema>;
declare const filterSchema: z.ZodUnion<[z.ZodString, z.ZodEffects<z.ZodNull, string, null>]>;
export type FilterInput = z.input<typeof filterSchema>;
export type FilterOutput = z.output<typeof filterSchema>;
declare const jsonSchema: z.ZodUnion<[z.ZodString, z.ZodArray<z.ZodString, "many">, z.ZodType<Json, z.ZodTypeDef, Json>]>;
export type JsonInput = z.input<typeof jsonSchema>;
export type JsonOutput = z.output<typeof jsonSchema>;
export declare const commandArgsSchema: z.ZodEffects<z.ZodObject<{
    filter: z.ZodUnion<[z.ZodString, z.ZodEffects<z.ZodNull, string, null>]>;
    json: z.ZodUnion<[z.ZodString, z.ZodArray<z.ZodString, "many">, z.ZodType<Json, z.ZodTypeDef, Json>]>;
    options: z.ZodObject<{
        args: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodType<Json, z.ZodTypeDef, Json>>>;
        color: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
        input: z.ZodDefault<z.ZodOptional<z.ZodEnum<["file", "json", "string"]>>>;
        output: z.ZodDefault<z.ZodOptional<z.ZodEnum<["pretty", "compact", "string", "json"]>>>;
        raw: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
        slurp: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
        sort: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    }, "strip", z.ZodTypeAny, {
        sort: boolean;
        color: boolean;
        input: "string" | "file" | "json";
        output: "string" | "json" | "pretty" | "compact";
        raw: boolean;
        slurp: boolean;
        args?: Record<string, Json> | undefined;
    }, {
        sort?: boolean | undefined;
        args?: Record<string, Json> | undefined;
        color?: boolean | undefined;
        input?: "string" | "file" | "json" | undefined;
        output?: "string" | "json" | "pretty" | "compact" | undefined;
        raw?: boolean | undefined;
        slurp?: boolean | undefined;
    }>;
}, "strip", z.ZodTypeAny, {
    filter: string;
    options: {
        sort: boolean;
        color: boolean;
        input: "string" | "file" | "json";
        output: "string" | "json" | "pretty" | "compact";
        raw: boolean;
        slurp: boolean;
        args?: Record<string, Json> | undefined;
    };
    json: string[] | Json;
}, {
    filter: string | null;
    options: {
        sort?: boolean | undefined;
        args?: Record<string, Json> | undefined;
        color?: boolean | undefined;
        input?: "string" | "file" | "json" | undefined;
        output?: "string" | "json" | "pretty" | "compact" | undefined;
        raw?: boolean | undefined;
        slurp?: boolean | undefined;
    };
    json: string[] | Json;
}>, {
    filter: string;
    options: {
        sort: boolean;
        color: boolean;
        input: "string" | "file" | "json";
        output: "string" | "json" | "pretty" | "compact";
        raw: boolean;
        slurp: boolean;
        args?: Record<string, Json> | undefined;
    };
    json: string[] | Json;
}, {
    filter: string | null;
    options: {
        sort?: boolean | undefined;
        args?: Record<string, Json> | undefined;
        color?: boolean | undefined;
        input?: "string" | "file" | "json" | undefined;
        output?: "string" | "json" | "pretty" | "compact" | undefined;
        raw?: boolean | undefined;
        slurp?: boolean | undefined;
    };
    json: string[] | Json;
}>;
export type CommandArgsInput = z.input<typeof commandArgsSchema>;
export type CommandArgsOutput = z.output<typeof commandArgsSchema>;
export declare const buildCommandFlags: (options: OptionsOutput) => string[];
export {};
