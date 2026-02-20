export interface PineParameter {
  id: string; // generated unique id for internal tracking
  name: string; // Display name "RSI Length"
  variableName: string; // "length"
  type: "int" | "float" | "bool" | "string" | "source" | "color" | "unknown";
  defaultValue: any;
  pineSource: string;
}

export interface ParseWarning {
  message: string;
  severity: "warning";
}

export interface ParseError {
  message: string;
  severity: "error";
}

export interface ParsedIndicator {
  name: string;
  type: "oscillator" | "overlay";
  version: string;
  parameters: PineParameter[];
  warnings: ParseWarning[];
  errors: ParseError[];
}

export const parsePineScript = (code: string): ParsedIndicator => {
  const warnings: ParseWarning[] = [];
  const errors: ParseError[] = [];
  const parameters: PineParameter[] = [];

  // Clean lines for easier processing
  const lines = code.split("\n");

  // 1. Detect Version
  const versionMatch = code.match(/\/\/@version=(\d+)/);
  const version = versionMatch ? `v${versionMatch[1]}` : "unknown";

  // 2. Detect Name and Type
  let name = "Untitled Indicator";
  let type: "oscillator" | "overlay" = "oscillator";
  let foundDeclaration = false;

  const indicatorMatch = code.match(/indicator\s*\(\s*(?:title\s*=\s*)?["']([^"']+)["']/);
  const strategyMatch = code.match(/strategy\s*\(\s*(?:title\s*=\s*)?["']([^"']+)["']/);

  if (indicatorMatch) {
    name = indicatorMatch[1];
    foundDeclaration = true;
  } else if (strategyMatch) {
    name = strategyMatch[1];
    foundDeclaration = true;
  } else {
    errors.push({ message: "Could not detect indicator() or strategy() declaration.", severity: "error" });
  }

  const overlayMatch = code.match(/overlay\s*=\s*(true|false)/);
  if (overlayMatch) {
    type = overlayMatch[1] === "true" ? "overlay" : "oscillator";
  }

  // 3. Extract Parameters (Simple Regex Approach for Proto)
  // Logic: look for `var = input...(def, "title")` pattern

  const inputPatterns = [
    { regex: /(\w+)\s*=\s*input\.int\s*\(\s*(\d+)\s*,\s*(?:title\s*=\s*)?["']([^"']+)["']/, type: "int" },
    { regex: /(\w+)\s*=\s*input\.float\s*\(\s*([\d.]+)\s*,\s*(?:title\s*=\s*)?["']([^"']+)["']/, type: "float" },
    { regex: /(\w+)\s*=\s*input\.bool\s*\(\s*(true|false)\s*,\s*(?:title\s*=\s*)?["']([^"']+)["']/, type: "bool" },
    { regex: /(\w+)\s*=\s*input\.string\s*\(\s*["']([^"']+)["']\s*,\s*(?:title\s*=\s*)?["']([^"']+)["']/, type: "string" },
    { regex: /(\w+)\s*=\s*input\.source\s*\(\s*(\w+)\s*,\s*(?:title\s*=\s*)?["']([^"']+)["']/, type: "source" },
    // Generic v4 style: input(14, "Length") - assumes int/float loosely
    { regex: /(\w+)\s*=\s*input\s*\(\s*([\d.]+)\s*,\s*(?:title\s*=\s*)?["']([^"']+)["']/, type: "float" }, 
  ];

  lines.forEach(line => {
    // Skip comments
    if (line.trim().startsWith("//")) return;

    for (const p of inputPatterns) {
      const match = line.match(p.regex as RegExp);
      if (match) {
        let val: any = match[2];
        if (p.type === "int") val = parseInt(match[2]);
        if (p.type === "float") val = parseFloat(match[2]);
        if (p.type === "bool") val = match[2] === "true";
        
        // Avoid duplicates if variable reused or re-declared (simple check)
        if (!parameters.find(x => x.variableName === match[1])) {
           parameters.push({
             id: Math.random().toString(36).substring(7),
             variableName: match[1],
             defaultValue: val,
             name: match[3],
             type: p.type as any,
             pineSource: match[0]
           });
        }
        break; // matched one pattern, move to next line
      }
    }

    // Warnings Checks
    if (line.includes("plot(") && line.includes("color=") && !line.includes("color.new") && !line.includes("input.color")) {
       // Simple heuristic for hardcoded colors
       // This is a bit loose but okay for prototype
       // warnings.push({ message: "Potential hardcoded color detected in plot().", severity: "warning" });
    }
    if (line.includes("security(")) {
       warnings.push({ message: "Uses security() function. Multi-timeframe data may require extra setup.", severity: "warning" });
    }
    if (line.includes("request.financial(")) {
        errors.push({ message: "Uses request.financial() which is not supported.", severity: "error" });
    }
  });

  return {
    name,
    type,
    version,
    parameters,
    warnings,
    errors
  };
};
