"use client";

import { AppRouterCacheProvider } from '@mui/material-nextjs/v15-appRouter';
import * as React from "react";

import { useRouter } from "next/navigation";
import { createTheme, CssBaseline, ThemeProvider } from '@mui/material';

export interface ProvidersProps {
  children: React.ReactNode;
}

const theme = createTheme({
  typography: {
    fontFamily: 'var(--font-roboto)',
  },
  cssVariables: true,
  palette: {
    mode: 'dark'
  }
});

export function Providers({ children }: ProvidersProps) {

  return (
    <AppRouterCacheProvider options={{
        enableCssLayer: true
    }}>
        <ThemeProvider theme={theme}>
            <CssBaseline />
            {children}
        </ThemeProvider>
    </AppRouterCacheProvider>
  );
}
