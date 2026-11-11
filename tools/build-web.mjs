import {cp,mkdir,writeFile} from 'node:fs/promises';
const root=new URL('../',import.meta.url),dest=new URL('dist/',root);
await mkdir(dest,{recursive:true});await cp(new URL('app/',root),dest,{recursive:true});
for(const name of ['LICENSE','NOTICE','LICENSE.MAKEHUMAN.md','ASSETS.md'])await cp(new URL(name,root),new URL(name,dest));
await writeFile(new URL('.nojekyll',dest),'');console.log('Static web app built in dist/');
