declare const exec: (command: string, args: string[], stdin: string, cwd?: string, detached?: boolean) => Promise<string>;
export default exec;
