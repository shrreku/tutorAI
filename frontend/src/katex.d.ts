declare module 'katex' {
  export interface KatexOptions {
    displayMode?: boolean;
    throwOnError?: boolean;
    strict?: boolean | string | ((errorCode: string, errorMsg: string, token?: unknown) => boolean | string | void);
    output?: 'html' | 'mathml' | 'htmlAndMathml';
    trust?: boolean;
  }

  export function renderToString(expression: string, options?: KatexOptions): string;

  const katex: {
    renderToString: typeof renderToString;
  };

  export default katex;
}
