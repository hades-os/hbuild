'use client'

import fetcher from "@/app/fetcher";
import { PackageHistoryList, PackageHistoryEntry } from '@/app/models' 

import useSWR from 'swr'
import { HBuildState, HBuildPackageType } from '@/app/models'
import { Suspense, useState } from "react";
import { ConsoleOut } from "@/app/components/ConsoleOut";
import { Chip, List, ListItem, ListItemButton, ListItemText, Dialog, DialogTitle, IconButton, DialogContent, DialogActions, Button, styled, TextField, Accordion, AccordionSummary, Typography, AccordionDetails, Collapse } from "@mui/material";
import CloseIcon from '@mui/icons-material/Close';
import { ExpandLess, ExpandMore, ListAlt } from "@mui/icons-material";

type ChipColor = 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'

const timestampToFormatted = (timestamp: number) => {
    const date = new Date(timestamp * 1000)
    return date.toISOString()
}

const PackageList = ({ packages } : { packages: string[] }) => {
  const [open, setOpen] = useState(true);

  const handlePress = () => setOpen(!open);

    return <>
        <Button onClick={handlePress} className="-ml-2.5 self-start" variant="text" color="inherit">
            <ListAlt /> Packages
            { open ? <ExpandLess /> : <ExpandMore /> }
        </Button>
        <Collapse in={open}  timeout="auto" unmountOnExit>
            <List>
                {packages.map(name => (
                    <ListItemText sx={{ pl: 4 }} primary={name} key={name} />
                ))}
            </List>                        
        </Collapse>    
    </>
}

export default () => {
    const { data, error, isLoading } = useSWR<PackageHistoryList>(
        'http://localhost:8000/api/history',
        fetcher
    )

    if (isLoading) {
        return <p>Loading...</p>
    }

    if (error) {
        throw Error('Failed to load history data')
    }

    return (
        <div className="mb-2">
            {data!.past_jobs.map(historyItem => (
                <Accordion key={historyItem.id}>
                    <AccordionSummary key={historyItem.id}>
                        <Typography component="span">Job {historyItem.id} - {historyItem.runner}</Typography>
                    </AccordionSummary>
                    <AccordionDetails className="flex flex-col">
                        <Typography component="span">Executed At {timestampToFormatted(historyItem.created_at)}</Typography>
                        <PackageList packages={historyItem.packages} />
                    </AccordionDetails>
                </Accordion>
            ))}
        </div>
    )
}
