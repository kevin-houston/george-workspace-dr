"use strict";
Object.defineProperty(exports, "__esModule", {
    value: true
});
Object.defineProperty(exports, "run", {
    enumerable: true,
    get: function() {
        return run;
    }
});
const _exec = /*#__PURE__*/ _interop_require_default(require("./exec"));
const _command = require("./command");
function _interop_require_default(obj) {
    return obj && obj.__esModule ? obj : {
        default: obj
    };
}
const run = (filter, json, options, cwd, detached)=>{
    return new Promise((resolve, reject)=>{
        const { command, args, stdin } = (0, _command.commandFactory)(filter, json, options);
        (0, _exec.default)(command, args, stdin, cwd, detached).then((stdout)=>{
            if (options?.output === 'json') {
                if (stdout === '') {
                    return resolve(undefined);
                }
                let result;
                try {
                    result = JSON.parse(stdout);
                } catch (_error) {
                    result = stdout;
                }
                return resolve(result);
            } else {
                return resolve(stdout);
            }
        }).catch(reject);
    });
};
