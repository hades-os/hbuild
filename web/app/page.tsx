'use client'

import {Chip} from "@heroui/chip";
import { Link } from "@heroui/link";
import { Snippet } from "@heroui/snippet";
import {Accordion, AccordionItem} from "@heroui/accordion";
import { Code } from "@heroui/code";
import { button as buttonStyles } from "@heroui/theme";
import fetcher from "@/app/fetcher";
import { PackageStatusList } from '@/app/models' 

import useSWR from 'swr'
import { HBuildState, HBuildPackageType } from '@/app/models'

type ChipColor = "default" | "primary" | "secondary" | "success" | "warning" | "danger"
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

    return (
        <Accordion>
            {data!.packages.map(packageStatusItem => (
                <AccordionItem
                    key={packageStatusItem.name}
                    title={<>
                        <h4>{packageStatusItem.name}</h4>
                        <Chip 
                            color={getChipColorByStatus(packageStatusItem.status)}
                            className="mr-2"
                        >{packageStatusItem.status}</Chip>
                        <Chip color={getChipColorByType(packageStatusItem.type)}>{packageStatusItem.type}</Chip>
                    </>}
                >
                    Description goes here
                </AccordionItem>
            ))}
        </Accordion>
    )
}
