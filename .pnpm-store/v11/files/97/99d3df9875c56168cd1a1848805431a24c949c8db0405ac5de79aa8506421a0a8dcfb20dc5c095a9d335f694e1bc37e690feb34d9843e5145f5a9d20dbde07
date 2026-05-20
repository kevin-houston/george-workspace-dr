"use strict";
Object.defineProperty(exports, "__esModule", {
    value: true
});
Object.defineProperty(exports, "commandFactory", {
    enumerable: true,
    get: function() {
        return commandFactory;
    }
});
const _nodepath = /*#__PURE__*/ _interop_require_wildcard(require("node:path"));
const _options = require("./options");
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
const JQ_PATH = process.env.JQ_PATH ?? process.env.npm_config_jq_path ?? _nodepath.join(__dirname, '..', 'bin', 'jq');
const validateArguments = (filter, json, options)=>{
    const validatedArgs = _options.commandArgsSchema.parse({
        filter,
        json,
        options
    });
    const flags = (0, _options.buildCommandFlags)(validatedArgs.options);
    const commandArgs = [
        ...flags,
        validatedArgs.filter
    ];
    let stdin = '';
    switch(validatedArgs.options?.input){
        case 'file':
            {
                const paths = validatedArgs.json;
                commandArgs.push(...typeof paths === 'string' ? [
                    paths
                ] : paths);
                break;
            }
        case 'json':
            {
                stdin = JSON.stringify(validatedArgs.json);
                break;
            }
        case 'string':
            {
                stdin = validatedArgs.json;
                break;
            }
    }
    return {
        args: commandArgs,
        stdin
    };
};
const commandFactory = (filter, json, options)=>{
    const { args, stdin } = validateArguments(filter, json, options ?? {});
    return {
        command: JQ_PATH,
        args,
        stdin
    };
};
