const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('luma', {
    language:(process.argv.find(value=>value.startsWith('--luma-language='))||'--luma-language=system').split('=')[1],
    systemLocale:(process.argv.find(value=>value.startsWith('--luma-system-locale='))||'--luma-system-locale=zh-CN').split('=')[1],
 call: (method, args = {}) => ipcRenderer.invoke('api', method, args),
 onOpenAccount: listener => {const handler=(_event,value)=>listener(value);ipcRenderer.on('open-account',handler);return ()=>ipcRenderer.removeListener('open-account',handler)},
    onLibrarySwitch: listener => {const handler=(_event,state)=>listener(state);ipcRenderer.on('library-switch',handler);return ()=>ipcRenderer.removeListener('library-switch',handler)},
 onAssistantChanged: listener => {const handler=()=>listener();ipcRenderer.on('assistant-changed',handler);return ()=>ipcRenderer.removeListener('assistant-changed',handler)},
 onCompletion: listener => {const handler=(_event,state)=>listener(state);ipcRenderer.on('completion',handler);return ()=>ipcRenderer.removeListener('completion',handler)},
 onPreferences: listener => {const handler=(_event,preferences)=>listener(preferences);ipcRenderer.on('preferences',handler);return ()=>ipcRenderer.removeListener('preferences',handler)}
});
