'use client'

import { Suspense, use, useEffect, useState } from 'react'

import { ServerSentEvent } from '@/app/models'
import { TextField } from '@mui/material'

const ConsoleOut = ({ name }: { name: string }): React.ReactNode => {
    const [ logMessages, setLogMessages ] = useState<string[]>([])
    useEffect(() => {
        const eventSource = new EventSource(`http://localhost:8000/api/log/${name}`)
        eventSource.addEventListener("log", (event) => {
            if (event.data) {
                setLogMessages([...logMessages, event.data])


                console.log(logMessages)
                console.log( event.data)
            }
        })

        eventSource.onerror = () => {
            console.error("Unable to connect to build server");
            eventSource.close()
        }

        return () => {
            eventSource.close()
        }
    }, [])

    return (
        <Suspense fallback={<p>Awaiting stream from build server...</p>}>
            <TextField
                fullWidth
                multiline
                disabled
                sx={{
                    fontFamily: 'monospace'
                }}

                label='Console Output'
                variant="standard"
                defaultValue={logMessages.join("\n")}
            />
        </Suspense>
    )
}

export { ConsoleOut }