"use strict";
Object.defineProperty(exports, "__esModule", {
    value: true
});
Object.defineProperty(exports, "default", {
    enumerable: true,
    get: function() {
        return _default;
    }
});
const _child_process = /*#__PURE__*/ _interop_require_default(require("child_process"));
const _stripfinalnewline = /*#__PURE__*/ _interop_require_default(require("strip-final-newline"));
function _interop_require_default(obj) {
    return obj && obj.__esModule ? obj : {
        default: obj
    };
}
const TEN_MEBIBYTE = 1024 * 1024 * 10;
const exec = (command, args, stdin, cwd, detached)=>{
    return new Promise((resolve, reject)=>{
        let stdout = '';
        let stderr = '';
        const spawnOptions = {
            maxBuffer: TEN_MEBIBYTE,
            cwd,
            detached,
            env: {}
        };
        const process = _child_process.default.spawn(command, args, spawnOptions);
        // All of these handlers can close the Promise, so guard against rejecting it twice.
        let promiseAlreadyRejected = false;
        process.on('close', (code)=>{
            if (!promiseAlreadyRejected) {
                promiseAlreadyRejected = true;
                if (code !== 0) {
                    return reject(Error(stderr));
                } else {
                    return resolve((0, _stripfinalnewline.default)(stdout));
                }
            }
        });
        if (stdin) {
            process.stdin.on('error', (err)=>{
                if (!promiseAlreadyRejected) {
                    promiseAlreadyRejected = true;
                    return reject(err);
                }
            });
            process.stdin.write(stdin);
            process.stdin.end();
        }
        process.stdout.setEncoding('utf-8');
        process.stdout.on('data', (data)=>{
            stdout += data;
        });
        process.stderr.on('data', (data)=>{
            stderr += data;
        });
    });
};
const _default = exec;
