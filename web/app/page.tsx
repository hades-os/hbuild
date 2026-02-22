'use client'

import fetcher from "@/app/fetcher";
import { PackageInfoList, PackageInfo } from '@/app/models' 

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
    const [openItem, setOpenItem] = useState(false);
    const [currentPackage, setCurrentPackage] = useState<PackageInfo>();

    const openPackageModal = (item: PackageInfo) => {
        setOpenItem(true);
        setCurrentPackage(item)
    }
    const { data, error, isLoading } = useSWR<PackageInfoList>(
        'http://localhost:8000/api/packages',
        fetcher
    )

    if (isLoading) {
        return <p>Loading...</p>
    }

    if (error) {
        throw Error('Failed to load package data')
    }

    const postBuild = (item: PackageInfo) => {
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
            {data!.packages.map(packageItem => (
                <ListItemButton
                    key={packageItem.name}
                    onClick={() => openPackageModal(packageItem)}
                >
                    <Chip 
                        label={packageItem.type}
                        color={getChipColorByType(packageItem.type)} className="mr-2"
                    />
                    <ListItemText primary={packageItem.name} />
                </ListItemButton>
            ))}
        </List>
        <PackageDialog
            onClose={() => setOpenItem(false)}
            aria-labelledby="item-status-title"
            open={openItem}
        >
            <DialogTitle sx={{ m: 0, p: 2 }} id="item-status-title">
                Package: {currentPackage?.name}
            </DialogTitle>
            <IconButton
                aria-label="close"
                onClick={() => setOpenItem(false)}
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
                    onClick={() => setOpenItem(false)}
                    color="error"
                >
                    Cancel Build
                </Button>
            </DialogActions>
        </PackageDialog>        
        </>
    )
}
