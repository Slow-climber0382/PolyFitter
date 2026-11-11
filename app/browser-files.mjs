function download(name,data){
 const url=URL.createObjectURL(new Blob([data],{type:'application/octet-stream'}));
 const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);return true;
}
if(!window.forgefit)window.forgefit={save:async(name,data)=>download(name,data),saveBatch:async(files)=>{for(const file of files)download(file.name,file.data);return true;}};
