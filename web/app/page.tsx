'use client'

import fetcher from "@/app/fetcher";
import { PackageStatusList, PackageStatus } from '@/app/models' 

import useSWR from 'swr'
import { HBuildState, HBuildPackageType } from '@/app/models'
import { Suspense, useState } from "react";
import { ConsoleOut } from "@/app/components/ConsoleOut";
import { Chip, List, ListItem, ListItemButton, ListItemText, Dialog, DialogTitle, IconButton, DialogContent, DialogActions, Button, styled, TextField } from "@mui/material";
import CloseIcon from '@mui/icons-material/Close';

const PackageDialog = styled(Dialog)(({ theme }) => ({
  '& .MuiDialogContent-root': {
    padding: theme.spacing(2),
  },
  '& .MuiDialogActions-root': {
    padding: theme.spacing(1),
  },
}));

type ChipColor = 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'
const getChipColorByStatus = (status: HBuildState): ChipColor => {
    switch(status) {
        case 'unbuilt': 
            return 'default'
        case 'configured':
            return 'primary'
        case 'built':
            return 'secondary'
        case 'installed':
            return 'success'
    }
}

const getChipColorByType = (type: HBuildPackageType): ChipColor => {
    switch (type) {
        case 'package':
            return 'primary'
        case 'tool':
            return 'secondary'
        case 'source':
            return 'success'
    }
}

export default () => {
    const [openItemStatus, setOpenItemStatus] = useState(false);
    const [currentPackage, setCurrentPackage] = useState<PackageStatus>();

    const openPackageModal = (item: PackageStatus) => {
        setOpenItemStatus(true);
        setCurrentPackage(item)
    }
    const { data, error, isLoading } = useSWR<PackageStatusList>(
        'http://localhost:8000/api/status',
        fetcher
    )

    if (isLoading) {
        return <p>Loading...</p>
    }

    if (error) {
        throw Error('Failed to load package data')
    }

    const postBuild = (item: PackageStatus) => {
        const req = {
            "build_to": item.type == "source" ? "build" : "install",
            "packages": [
                {
                    "name": item.name,
                    "stage": null
                }
            ]
        }

        fetch(`http://localhost:8000/api/build`, {
            method: 'POST',
            body: JSON.stringify(req),
            headers: {
                "Content-Type":"application/json"
            }
        })
            .then(res => {
                if (res.status != 202) {
                    /*addToast({
                        title: "Error",
                        description: "Unable to send build request to server",
                        color: "danger"
                    })*/
                }
            })
    }

    return (
        <>
        <List
            sx={{
                marginBottom: 2
            }}
        >
            {data!.packages.map(packageStatusItem => (
                <ListItemButton
                    key={packageStatusItem.name}
                    onClick={() => openPackageModal(packageStatusItem)}
                >
                    <Chip 
                        label={packageStatusItem.status}
                        color={getChipColorByStatus(packageStatusItem.status)} className="mr-2" 
                    />
                    <Chip 
                        label={packageStatusItem.type}
                        color={getChipColorByType(packageStatusItem.type)} className="mr-2"
                    />
                    <ListItemText primary={packageStatusItem.name} />
                </ListItemButton>
            ))}
        </List>
        <PackageDialog
            onClose={() => setOpenItemStatus(false)}
            aria-labelledby="item-status-title"
            open={openItemStatus}
        >
            <DialogTitle sx={{ m: 0, p: 2 }} id="item-status-title">
                Package: {currentPackage?.name}
            </DialogTitle>
            <IconButton
                aria-label="close"
                onClick={() => setOpenItemStatus(false)}
                sx={(theme) => ({
                    position: 'absolute',
                    right: 8,
                    top: 8,
                    color: theme.palette.grey[500]
                })}
            >
                <CloseIcon />
            </IconButton>
            <DialogContent dividers className="w-xl">
                {currentPackage ? <ConsoleOut name={currentPackage.name} /> : <></>}
            </DialogContent>
            <DialogActions>
                <Button
                    onClick={() => postBuild(currentPackage!)}
                    color="primary"
                >
                    Build Now
                </Button>
                <Button 
                    onClick={() => setOpenItemStatus(false)}
                    color="error"
                >
                    Cancel Build
                </Button>
            </DialogActions>
        </PackageDialog>        
        </>
    )
}
