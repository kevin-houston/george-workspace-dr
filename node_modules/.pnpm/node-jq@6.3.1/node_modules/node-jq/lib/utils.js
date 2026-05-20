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
    isJSONPath: function() {
        return isJSONPath;
    },
    isStringArray: function() {
        return isStringArray;
    }
});
const isStringArray = (values)=>values.every((value)=>typeof value === 'string');
const isJSONPath = (path)=>{
    return /\.json|.jsonl$/.test(path);
};
