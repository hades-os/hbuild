'use client'

import { useRouter } from 'next/navigation'

import "@/styles/globals.css";
import clsx from "clsx";

import { Providers } from "./providers";

import { fontSans } from "@/config/fonts";
import fetcher from "@/app/fetcher";

import useSWR from 'swr'
import { createTheme, styled } from '@mui/material/styles';
import { Roboto } from 'next/font/google';
import { ThemeProvider } from '@mui/material/styles';
import { Box, Collapse, Container, Divider, Drawer, IconButton, List, ListItem, ListItemButton, ListItemText, Toolbar, Typography } from "@mui/material";
import MuiAppBar, { AppBarProps as MuiAppBarProps } from '@mui/material/AppBar';
import { useState } from "react";
import MenuIcon from '@mui/icons-material/Menu';
import { ChevronLeft, ExpandLess, ExpandMore } from "@mui/icons-material";

const theme = createTheme({
  typography: {
    fontFamily: 'var(--font-roboto)',
  },
  cssVariables: true,
  palette: {
    mode: 'dark'
  }
});

const roboto = Roboto({
  weight: ['300', '400', '500', '700'],
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-roboto',
});

const Main = styled('main', { shouldForwardProp: (prop) => prop !== 'open' })<{
  open?: boolean;
}>(({ theme }) => ({
  flexGrow: 1,
  padding: theme.spacing(3),
  transition: theme.transitions.create('margin', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  marginLeft: `-${drawerWidth}px`,
  variants: [
    {
      props: ({ open }) => open,
      style: {
        transition: theme.transitions.create('margin', {
          easing: theme.transitions.easing.easeOut,
          duration: theme.transitions.duration.enteringScreen,
        }),
        marginLeft: 0,
      },
    },
  ],
}));

interface AppBarProps extends MuiAppBarProps {
  open?: boolean;
}

const AppBar = styled(MuiAppBar, {
  shouldForwardProp: (prop) => prop !== 'open',
})<AppBarProps>(({ theme }) => ({
  transition: theme.transitions.create(['margin', 'width'], {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  variants: [
    {
      props: ({ open }) => open,
      style: {
        width: `calc(100% - ${drawerWidth}px)`,
        marginLeft: `${drawerWidth}px`,
        transition: theme.transitions.create(['margin', 'width'], {
          easing: theme.transitions.easing.easeOut,
          duration: theme.transitions.duration.enteringScreen,
        }),
      },
    },
  ],
}));

const drawerWidth = 240;
const DrawerHeader = styled('div')(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  padding: theme.spacing(0, 1),
  ...theme.mixins.toolbar,
  justifyContent: 'flex-end',
}));

export default ({ children } 
    : { children: React.ReactNode }) => {
    const [open, setOpen] = useState(false);
    const [openBuildQueue, setOpenBuildQueue] = useState(false)

    const handleDrawerOpen = () => setOpen(true);
    const handleDrawerClose = () => setOpen(false);

    const router = useRouter()

    return (
        <html suppressHydrationWarning lang="en" className={roboto.variable}>
        <head />
        <body>
        <Providers>
            <Box
                sx={{
                    display: 'flex'
                }}
            >
                <AppBar 
                    position="fixed" 
                    open={open}
                >
                    <Toolbar>
                        <IconButton
                            color="inherit"
                            aria-label="Open Menu"
                            onClick={handleDrawerOpen}
                            edge="start"
                            sx={[
                                {
                                    mr: 2
                                },

                                open && { display: 'none' }
                            ]}
                        >
                            <MenuIcon />
                        </IconButton>
                        <Typography
                            variant="h6"
                            noWrap
                            component="div"
                        >HBuild Server</Typography>
                    </Toolbar>
                </AppBar>
                <Drawer
                    sx={{
                        width: drawerWidth,
                        flexShrink: 0,
                        '& .MuiDrawer-paper': {
                            width: drawerWidth,
                            boxSizing: 'border-box'
                        }
                    }}

                    variant="persistent"
                    anchor="left"
                    open={open}
                >
                    <DrawerHeader>
                        <IconButton onClick={handleDrawerClose}>
                            <ChevronLeft />
                        </IconButton>
                    </DrawerHeader>
                    <Divider />
                    <List>
                        {Object.entries({
                            'Home': '/', 
                            'Build History': '/history', 
                            'Dependency Graph': '/graph'
                        }).map(([text, url]) => (
                            <ListItem
                                key={text} 
                                disablePadding
                            >
                                <ListItemButton onClick={() => router.push(url)}>
                                    <ListItemText primary={text} />
                                </ListItemButton>
                            </ListItem>
                        ))}
                        <ListItemButton onClick={() => setOpenBuildQueue(prev => !prev)}>
                            <ListItemText primary="Build Queue" />
                            {openBuildQueue ? <ExpandLess /> : <ExpandMore /> }
                        </ListItemButton>
                        <Collapse in={openBuildQueue} timeout="auto" unmountOnExit>
                            <List component="div" disablePadding>
                                { /* Add in build queue functions  */ }
                                <ListItem sx={{ pl: 4 }}>
                                    <ListItemText primary="-" />
                                </ListItem>                                
                            </List>
                        </Collapse>
                    </List>
                </Drawer>
                <Main open={open} className="flex flex-col w-full h-full">
                    <DrawerHeader />
                    {children}
                </Main>
            </Box>
        </Providers>
        </body>
        </html>
    );
}
