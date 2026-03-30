export interface ValidationResult {
  isValid: boolean;
  error: string | null;
}

export const validateParam = (key: string, value: string): ValidationResult => {
  // Allow empty strings while typing, validation will catch them as active errors if needed
  // or we can treat empty as invalid. Assuming strict validation for RUN:
  if (value === "") return { isValid: false, error: "Required" };

  const rules: Record<string, (v: string) => string | null> = {
    // Integer params
    rsi_period: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n < 2) return "RSI period must be ≥ 2";
      if (n > 100) return "RSI period must be ≤ 100";
      return null;
    },
    ema_fast: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n < 1) return "EMA Fast must be ≥ 1";
      return null;
    },
    ema_slow: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n < 1) return "EMA Slow must be ≥ 1";
      return null;
    },
    leverage: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n < 1 || n > 125) return "Leverage must be 1-125";
      return null;
    },

    // Decimal params
    risk_percent: (v) => {
      const n = parseFloat(v);
      if (isNaN(n) || n <= 0) return "Risk must be > 0%";
      if (n > 100) return "Risk cannot exceed 100%";
      return null;
    },
    tp1_rr: (v) => {
      const n = parseFloat(v);
      if (isNaN(n) || n <= 0) return "TP1 R:R must be > 0";
      return null;
    },
    sl_buffer_pct: (v) => {
      const n = parseFloat(v);
      if (isNaN(n) || n < 0) return "SL buffer cannot be negative";
      return null;
    },
    capital: (v) => {
        const n = parseFloat(v);
        if (isNaN(n) || n <= 0) return "Capital must be > 0";
        return null;
    }
  };

  const validator = rules[key];
  const error = validator ? validator(value) : null;
  return { isValid: !error, error };
};

// Schema-aware validation (used by DynamicParamForm)
export const validateFromSchema = (
  key: string,
  value: string,
  schema?: any
): ValidationResult => {
  if (value === "") return { isValid: false, error: "Required" };

  const prop = schema?.properties?.[key];
  if (!prop) {
    const n = parseFloat(value);
    if (isNaN(n)) return { isValid: false, error: "Must be a number" };
    return { isValid: true, error: null };
  }

  if (prop.type === "integer" || prop.type === "number") {
    const n = prop.type === "integer" ? parseInt(value) : parseFloat(value);
    if (isNaN(n)) return { isValid: false, error: `${prop.title} must be a number` };
    if (prop.minimum !== undefined && n < prop.minimum)
      return { isValid: false, error: `Min: ${prop.minimum}` };
    if (prop.maximum !== undefined && n > prop.maximum)
      return { isValid: false, error: `Max: ${prop.maximum}` };
  }

  if (prop.enum && !prop.enum.includes(value)) {
    return { isValid: false, error: `Must be one of: ${prop.enum.join(", ")}` };
  }

  return { isValid: true, error: null };
};
