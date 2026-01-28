"use client";

import { AppRouterCacheProvider } from '@mui/material-nextjs/v15-appRouter';
import * as React from "react";

import { useRouter } from "next/navigation";
import { CssBaseline } from '@mui/material';

export interface ProvidersProps {
  children: React.ReactNode;
}

export function Providers({ children }: ProvidersProps) {

  return (
    <AppRouterCacheProvider options={{
        enableCssLayer: true
    }}>
        <CssBaseline />
        {children}
    </AppRouterCacheProvider>
  );
}
