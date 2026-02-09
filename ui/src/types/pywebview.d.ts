declare global {
  interface Window {
    pywebview: {
      api: {
        get_strategies: () => Promise<string[]>;
        // ... other methods will be added later
      }
    }
  }
}
