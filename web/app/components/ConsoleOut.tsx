'use client'

import { Suspense, use, useEffect, useState } from 'react'

import { LogEvent, LogEventStream } from '@/app/models'
import { TextField, Typography } from '@mui/material'
import useSWR from 'swr'
import fetcher from "@/app/fetcher";

const ConsoleOut = ({ name }: { name: string }): React.ReactNode => {
    const { data, error, isLoading } = useSWR<LogEventStream>(`http://localhost:8000/api/log/${name}`, fetcher, { 
        refreshInterval: 1000
    })

    return (
        <Suspense fallback={<p>Awaiting stream from build server...</p>}>
            {isLoading ? 
                <Typography>
                    Loading log stream, please wait...
                </Typography> :
              error ?
                <Typography color="error">
                    Failed to load log stream!
                </Typography>
                :
                <TextField
                    fullWidth
                    multiline
                    disabled
                    sx={{
                        fontFamily: 'monospace',  
                        backgroundColor: '#121212',
                        input: {
                            color: 'white'
                        }
                    }}                    

                    label='Console Output'
                    variant="standard"
                    defaultValue={data!.logs.map(event => event.log).join("")}
            />}
        </Suspense>
    )
}

export { ConsoleOut }