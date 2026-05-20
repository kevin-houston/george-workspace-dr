"use strict";
Object.defineProperty(exports, "__esModule", {
    value: true
});
function _export(target, all) {
    for(var name in all)Object.defineProperty(target, name, {
        enumerable: true,
        get: all[name]
    });
}
_export(exports, {
    buildCommandFlags: function() {
        return buildCommandFlags;
    },
    commandArgsSchema: function() {
        return commandArgsSchema;
    },
    jsonTypeSchema: function() {
        return jsonTypeSchema;
    },
    optionsSchema: function() {
        return optionsSchema;
    }
});
const _isvalidpath = /*#__PURE__*/ _interop_require_default(require("is-valid-path"));
const _zod = /*#__PURE__*/ _interop_require_wildcard(require("zod"));
const _utils = require("./utils");
function _interop_require_default(obj) {
    return obj && obj.__esModule ? obj : {
        default: obj
    };
}
function _getRequireWildcardCache(nodeInterop) {
    if (typeof WeakMap !== "function") return null;
    var cacheBabelInterop = new WeakMap();
    var cacheNodeInterop = new WeakMap();
    return (_getRequireWildcardCache = function(nodeInterop) {
        return nodeInterop ? cacheNodeInterop : cacheBabelInterop;
    })(nodeInterop);
}
function _interop_require_wildcard(obj, nodeInterop) {
    if (!nodeInterop && obj && obj.__esModule) {
        return obj;
    }
    if (obj === null || typeof obj !== "object" && typeof obj !== "function") {
        return {
            default: obj
        };
    }
    var cache = _getRequireWildcardCache(nodeInterop);
    if (cache && cache.has(obj)) {
        return cache.get(obj);
    }
    var newObj = {
        __proto__: null
    };
    var hasPropertyDescriptor = Object.defineProperty && Object.getOwnPropertyDescriptor;
    for(var key in obj){
        if (key !== "default" && Object.prototype.hasOwnProperty.call(obj, key)) {
            var desc = hasPropertyDescriptor ? Object.getOwnPropertyDescriptor(obj, key) : null;
            if (desc && (desc.get || desc.set)) {
                Object.defineProperty(newObj, key, desc);
            } else {
                newObj[key] = obj[key];
            }
        }
    }
    newObj.default = obj;
    if (cache) {
        cache.set(obj, newObj);
    }
    return newObj;
}
const JSON_INVALID_PATH_TYPE_ERROR = 'invalid json argument supplied (expected a string or an array of strings)';
const JSON_INVALID_PATH_ERROR = 'invalid json argument supplied (not a valid path)';
const JSON_NOT_A_JSON_FILE_ERROR = 'invalid json argument supplied (not a .json file)';
const literalSchema = _zod.union([
    _zod.string(),
    _zod.number(),
    _zod.boolean(),
    _zod.null()
]);
const jsonTypeSchema = _zod.lazy(()=>_zod.union([
        literalSchema,
        _zod.array(jsonTypeSchema),
        _zod.record(jsonTypeSchema)
    ]));
const optionsSchema = _zod.object({
    args: _zod.record(jsonTypeSchema).optional(),
    color: _zod.boolean().optional().default(false),
    input: _zod.enum([
        'file',
        'json',
        'string'
    ]).optional().default('file'),
    output: _zod.enum([
        'pretty',
        'compact',
        'string',
        'json'
    ]).optional().default('pretty'),
    raw: _zod.boolean().optional().default(false),
    slurp: _zod.boolean().optional().default(false),
    sort: _zod.boolean().optional().default(false)
});
const filterSchema = _zod.union([
    _zod.string(),
    _zod.null().transform(()=>'null')
]);
const jsonSchema = _zod.union([
    _zod.string(),
    _zod.array(_zod.string()),
    jsonTypeSchema
]);
const commandArgsSchema = _zod.object({
    filter: filterSchema,
    json: jsonSchema,
    options: optionsSchema
}).superRefine((data, ctx)=>{
    const json = data.json;
    const input = data.options.input;
    switch(input){
        case 'file':
            {
                const paths = [];
                if (typeof json === 'string') {
                    paths.push(json);
                } else if (Array.isArray(json) && (0, _utils.isStringArray)(json)) {
                    paths.concat(json);
                } else {
                    ctx.addIssue({
                        code: _zod.ZodIssueCode.custom,
                        fatal: true,
                        message: JSON_INVALID_PATH_TYPE_ERROR
                    });
                    return _zod.NEVER;
                }
                paths.forEach((path)=>{
                    if (!(0, _isvalidpath.default)(path)) {
                        ctx.addIssue({
                            code: _zod.ZodIssueCode.custom,
                            fatal: true,
                            message: `${JSON_INVALID_PATH_ERROR}: "${path}"`
                        });
                        return;
                    }
                    if (!(0, _utils.isJSONPath)(path)) {
                        ctx.addIssue({
                            code: _zod.ZodIssueCode.custom,
                            fatal: true,
                            message: `${JSON_NOT_A_JSON_FILE_ERROR}: "${path}"`
                        });
                        return;
                    }
                });
                break;
            }
        case 'string':
            {
                if (typeof json !== 'string') {
                    ctx.addIssue({
                        code: _zod.ZodIssueCode.invalid_type,
                        expected: 'string',
                        fatal: true,
                        received: typeof json
                    });
                } else if (json === '') {
                    ctx.addIssue({
                        code: _zod.ZodIssueCode.too_small,
                        fatal: true,
                        inclusive: true,
                        minimum: 1,
                        type: 'string'
                    });
                }
                break;
            }
    }
    return _zod.NEVER;
});
const buildCommandFlags = (options)=>{
    const flags = [];
    options.color && flags.push('--color-output');
    options.raw && flags.push('-r');
    options.slurp && flags.push('--slurp');
    options.sort && flags.push('--sort-keys');
    if ([
        'compact',
        'string'
    ].includes(options.output)) {
        flags.push('--compact-output');
    }
    Object.entries(options.args ?? {}).forEach(([key, value])=>{
        if (typeof value === 'string') {
            flags.push('--arg', key, value);
            return;
        }
        flags.push('--argjson', key, JSON.stringify(value));
    });
    return flags;
};
