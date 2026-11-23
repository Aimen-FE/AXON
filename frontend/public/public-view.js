(()=>{
 const offline=document.body.dataset.mode==='offline';
 fetch(offline?'./axon-offline-public.json':'./api/public/info',{credentials:'omit',cache:'no-store'}).then(async response=>{if(!response.ok)throw Error('unavailable');return response.json()}).then(info=>{
  if(!info.center)throw Error('empty');
  document.getElementById('state').textContent=offline?'Información pública autorizada el '+new Date(info.authorized_at).toLocaleDateString('es-ES')+'.':info.demo?'Demostración con datos ficticios.':'Información pública del centro.';
  const center=document.getElementById('center'),heading=document.createElement('h2'),town=document.createElement('p');heading.textContent=info.center.name;town.textContent=info.center.town;center.append(heading,town);
  const list=document.getElementById('documents');
  for(const doc of info.documents||[]){const item=document.createElement('li');item.textContent=doc.title;list.append(item)}
  if(!list.children.length){const item=document.createElement('li');item.textContent='No hay documentos públicos validados disponibles.';list.append(item)}
 }).catch(()=>{document.getElementById('state').textContent=offline?'No hay una copia pública autorizada y vigente en este navegador.':'No se pudo consultar la información pública. Comprueba que AXON está iniciado.'});
})();
