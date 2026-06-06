import type { MathfieldElement, MathfieldElementAttributes } from "mathlive";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "math-field": React.DetailedHTMLProps<
        React.HTMLAttributes<MathfieldElement>,
        MathfieldElement
      > &
        Partial<MathfieldElementAttributes>;
    }
  }
}
