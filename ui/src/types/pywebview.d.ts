declare global {
  interface Window {
    pywebview: {
      api: {
        get_strategies: () => Promise<string[]>;
      }
    }
  }
}

export {}
