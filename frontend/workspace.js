"use strict";
const $ = id => document.getElementById(id);
const state = {site:"", sites:[], units:[], datasets:[], record:null, code:null, busy:false};
let viewer = null;
function notice(message, error=false) { $("notice").textContent=message; $("notice").classList.toggle("error",error); }
async function api(path, body, method) {
  const response=await fetch(path,{method:method || (body===undefined?"GET":"POST"),
    headers:body===undefined?{}:{"Content-Type":"application/json"}, body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json().catch(()=>({detail:"The server returned an unreadable response."}));
  if(!response.ok) throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail || data));
  return data;
}
const scoped = path => path+(path.includes("?")?"&":"?")+"site_id="+encodeURIComponent(state.site);
const values = form => Object.fromEntries(new FormData(form));
function options(id, rows, label, blank="Choose…") {
  const node=$(id), old=node.value; node.replaceChildren(new Option(blank,""));
  rows.forEach(r=>node.add(new Option(label(r),r.id || r.uuid)));
  if([...node.options].some(o=>o.value===old)) node.value=old;
}
function list(id, rows, render, empty) {
  $(id).replaceChildren();
  rows.forEach(row=>{const li=document.createElement("li"); render(li,row); $(id).append(li);});
  if(!rows.length) {const li=document.createElement("li");li.textContent=empty;$(id).append(li);}
}
function lines(node, entries) {
  const dl=document.createElement("dl");
  entries.forEach(([label,value])=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=label;dd.textContent=value??"—";dl.append(dt,dd);});
  node.replaceChildren(dl);
}
function lock() {
  $("site").disabled=state.busy;
  $("siteTools").disabled=state.busy || !state.site;
  $("recordTools").disabled=state.busy || !state.record || state.record.status!=="ACTIVE";
  $("versions").disabled=state.busy;
  document.querySelectorAll("#createSite input,#createSite button").forEach(n=>n.disabled=state.busy);
  $("issue").disabled=state.record?.topology_status!=="VALID" || !state.record?.display_id.startsWith("UNISSUED/");
  $("citygml").disabled=state.record?.su_class!=="BUILDING";
}
async function action(work, success) {
  if(state.busy) return;
  state.busy=true; lock(); notice("Working…");
  try {await work(); if(success)notice(success);} catch(e){notice(e.message,true);}
  finally{state.busy=false;lock();}
}
function submit(id,work,success){$(id).addEventListener("submit",e=>{e.preventDefault();const payload=values(e.target);action(()=>work(payload,e.target),success);});}
function button(id,work,success){$(id).onclick=()=>action(work,success);}
function clearRecord(){state.record=null;state.code=null;$("record").hidden=true;$("emptyRecord").hidden=false;$("versions").replaceChildren();lock();}
async function loadSites(preferred=state.site) {
  state.sites=(await api("/sites")).sites;
  options("site",state.sites,r=>r.name,"Choose a site"); $("site").value=preferred;
  state.site=$("site").value;
}
async function directories(){const [p,b]=await Promise.all([api("/parties"),api("/baunits")]);options("party",p.parties,r=>r.name);options("baunit",b.baunits,r=>r.name || r.uid || r.id);}
async function refresh() {
  if(!state.site)return;
  const [u,d]=await Promise.all([api(scoped("/spatial-units")),api("/datasets")]);
  state.units=u.units;state.datasets=d.datasets.filter(r=>r.site_id===state.site);
  $("count").textContent=state.units.length;
  const floors=state.units.filter(r=>r.su_class==="FLOOR");options("floor",floors,r=>r.local_code,"All floors");
  const zs=state.units.flatMap(r=>[r.zmin,r.zmax]);$("height").min=zs.length?Math.min(...zs):0;$("height").max=zs.length?Math.max(...zs):1;$("height").value=$("height").max;
  renderUnits(); drawMap(); renderDatasets();
  const site=state.sites.find(r=>r.id===state.site);$("siteInfo").textContent=(site?.name || "Site")+" · Parent "+(site?.parent_ulpin || "")+" · Local metre heights";
  options("parcel",state.units.filter(r=>r.su_class==="PARCEL").map(r=>({...r,id:r.local_code})),r=>r.local_code);
  for(const [id,kind] of [["cloud","las"],["dsm","dsm"],["dtm","dtm"]])options(id,state.datasets.filter(d=>d.kind===kind),d=>d.filename);
  options("plans",state.datasets.filter(d=>!["las","dsm","dtm","derived-building"].includes(d.kind)),d=>d.filename,"No plans — estimates require review");
  if(state.code){const rec=state.units.find(r=>r.local_code===state.code);if(rec)await selectUnit(rec.uuid);else clearRecord();}
}
function renderUnits() {
  const query=$("search").value.toLowerCase();
  list("units",state.units.filter(r=>(r.local_code+" "+r.su_class).toLowerCase().includes(query)),(li,r)=>{
    const b=document.createElement("button");b.type="button";b.textContent=r.local_code+" · "+r.su_class+" · "+r.topology_status;
    b.classList.toggle("selected",r.local_code===state.code);b.onclick=()=>action(()=>selectUnit(r.uuid));li.append(b);
  },state.units.length?"No matching properties.":"No properties yet. Import and process a GeoJSON source.");
}
async function selectUnit(id, history=false) {
  const rec=await api("/records/"+encodeURIComponent(id));state.record=rec;state.code=rec.local_code;
  $("record").hidden=false;$("emptyRecord").hidden=true;$("propertyTitle").textContent=rec.local_code+" · "+rec.su_class;
  lines($("recordSummary"),[["Status",rec.status+" / "+rec.topology_status],["Identifier",rec.display_id],["Height",rec.zmin+" to "+rec.zmax+" m"],["Volume",Number(rec.volume_m3||0).toFixed(2)+" m³"],["Origin",rec.geom_origin],["Lifecycle",rec.status_reason]]);
  if(!history){const v=await api(scoped("/spatial-units/by-code/"+encodeURIComponent(rec.local_code)+"/versions"));options("versions",v.versions,r=>"Version "+r.version+" · "+r.status);}
  $("versions").value=rec.uuid;
  const src=rec.source;lines($("evidence"),src?[["Source",src.filename],["Checksum",src.checksum_sha256],["Source CRS","EPSG:"+src.epsg],["Assumptions",(src.processing?.assumptions || []).join("; ")],["Construction",src.construction?.method]]:[["Source","No imported source linked (demo record)."]]);
  listContent($("rightsHistory"),(rec.rrr || []).map(r=>r.rrr_type+" · "+r.party_name+" · share "+(r.share??"unspecified")+" · "+r.claim_status+" · "+(r.evidence_ref || "No evidence reference")),"No rights recorded.");
  listContent($("reviewsHistory"),(rec.reviews || []).map(r=>r.decision+" · "+r.reviewer_label+" · "+new Date(r.created_at).toLocaleString()+" · "+r.reason+" · "+(r.evidence_ref || "No evidence reference")),"No reviews recorded.");
  if(rec.baunit_id)$("baunit").value=rec.baunit_id;
  if(viewer) viewer.selectedEntity=viewer.entities.getById(rec.uuid);
  renderUnits();lock();
}
function listContent(node,strings,empty){node.replaceChildren();(strings.length?strings:[empty]).forEach(s=>{const p=document.createElement("p");p.className="hint";p.textContent=s;node.append(p);});}
function renderDatasets(){list("datasets",state.datasets,(li,d)=>{
  const name=document.createElement("div");name.textContent=d.filename+" · "+d.kind;li.append(name);
  if(!["las","dsm","dtm"].includes(d.kind)) {const b=document.createElement("button");b.type="button";b.textContent=d.meta.processed_unit_ids?"Already processed — reload":"Create properties from source";
    b.onclick=()=>action(async()=>{await api("/datasets/"+d.id+"/process",{});await refresh();},"Source processed. Properties remain subject to validation and explicit issuance.");li.append(b);}
  const inspect=document.createElement("button");inspect.type="button";inspect.textContent="View source details";inspect.onclick=()=>action(async()=>{const source=await api("/datasets/"+d.id);const details=document.createElement("pre");details.textContent=JSON.stringify({checksum:source.checksum_sha256,epsg:source.epsg,vertical_reference:source.z_ref,assumptions:source.meta.processing?.assumptions,local_zero_m:source.meta.local_zero_m},null,2);li.querySelector("pre")?.remove();li.append(details);});li.append(inspect);
},"No uploaded sources for this site.");}
function initMap(){try{
  if(!window.Cesium)throw new Error("3D viewer could not load. Check internet access and reload; forms and records remain available.");
  $("mapStatus").remove();viewer=new Cesium.Viewer("map",{baseLayer:false,baseLayerPicker:false,animation:false,timeline:false,geocoder:false,homeButton:false,sceneModePicker:false,infoBox:false,selectionIndicator:true,terrainProvider:new Cesium.EllipsoidTerrainProvider()});
  viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString("#244452");
  viewer.scene.screenSpaceCameraController.enableCollisionDetection=false;
  const handler=new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);handler.setInputAction(e=>{const picked=viewer.scene.pick(e.position);if(picked?.id?.id && state.units.some(u=>u.uuid===picked.id.id))action(()=>selectUnit(picked.id.id));},Cesium.ScreenSpaceEventType.LEFT_CLICK);
}catch(e){viewer=null;const p=document.createElement("p");p.textContent=e.message;$("map").replaceChildren(p);}}
function polygonHierarchy(gj){return new Cesium.PolygonHierarchy(gj.coordinates[0].map(([x,y])=>Cesium.Cartesian3.fromDegrees(x,y)),gj.coordinates.slice(1).map(r=>new Cesium.PolygonHierarchy(r.map(([x,y])=>Cesium.Cartesian3.fromDegrees(x,y)))));}
function drawMap(){if(!viewer)return;viewer.entities.removeAll();state.units.forEach(r=>{const gj=typeof r.geojson==="string"?JSON.parse(r.geojson):r.geojson;const color={VALID:"#39a7da",INVALID:"#ed6459",DEGRADED:"#e8ae47",PENDING:"#aebbc3"}[r.topology_status] || "#aebbc3";
  viewer.entities.add({id:r.uuid,name:r.local_code,polygon:{hierarchy:polygonHierarchy(gj),height:r.zmin,extrudedHeight:r.zmax,material:Cesium.Color.fromCssColorString(color).withAlpha(["PARCEL","BUILDING"].includes(r.su_class)?.12:.65),outline:true,outlineColor:Cesium.Color.WHITE}});
});filters();if(state.units.length)viewer.zoomTo(viewer.entities);}
function filters(){const floor=$("floor").value,cut=Number($("height").value),all=cut>=Number($("height").max);$("heightLabel").textContent=all?"All":cut+" m";
  if(!viewer)return;viewer.scene.globe.show=!$("underground").checked;
  state.units.forEach(r=>{let inFloor=!floor || r.uuid===floor || r.parent_id===floor;const e=viewer.entities.getById(r.uuid);if(e)e.show=inFloor && (all || r.zmin<=cut) && (r.su_class!=="BUILDING" || (!floor && all));});}
async function download(path,name){const r=await fetch(path);if(!r.ok){const data=await r.json();throw new Error(data.detail || "Export failed");}const url=URL.createObjectURL(await r.blob()),a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$("site").onchange=()=>action(async()=>{state.site=$("site").value;clearRecord();state.units=[];state.datasets=[];renderUnits();if(viewer)viewer.entities.removeAll();$("findings").replaceChildren();$("processingResult").replaceChildren();if(state.site)await refresh();else $("siteInfo").textContent="Choose or create a site to begin.";},"Site selection updated.");
$("search").oninput=renderUnits;$("floor").onchange=filters;$("height").oninput=filters;$("underground").onchange=filters;$("fit").onclick=()=>{if(viewer && state.units.length)viewer.zoomTo(viewer.entities);};
$("versions").onchange=()=>{if($("versions").value)action(()=>selectUnit($("versions").value,true));};
$("uploadKind").onchange=()=>{const elevation=$("uploadKind").value!=="plans";$("elevationFields").hidden=!elevation;$("sourceFile").accept=elevation?($("uploadKind").value==="las"?".las,.laz":".tif,.tiff"):".json,.geojson";};
$("processMode").onchange=()=>{const cloud=$("processMode").value==="cloud";$("cloudLabel").hidden=!cloud;$("rasterFields").hidden=cloud;};
submit("createSite",async(v,f)=>{const site=await api("/sites",{...v,epsg:Number(v.epsg)});clearRecord();await loadSites(site.id);await refresh();f.reset();},"Site created. Import a source to add properties.");
submit("upload",async(v,f)=>{const file=f.elements.file.files[0];if(file.size>64*1024*1024)throw new Error("Choose a file smaller than 64 MiB.");
  if(v.kind==="plans"){if(!v.epsg)throw new Error("Enter the GeoJSON source EPSG.");let geojson;try{geojson=JSON.parse(await file.text());}catch{throw new Error("The selected file is not valid JSON.");}await api("/datasets",{site_id:state.site,filename:file.name,kind:v.kind,epsg:Number(v.epsg),geom_origin:v.geom_origin,geojson});}
  else {const params=new URLSearchParams({site_id:state.site,kind:v.kind,filename:file.name,geom_origin:v.geom_origin,z_ref:v.z_ref});if(v.epsg)params.set("epsg",v.epsg);if(v.local_zero_m!=="")params.set("local_zero_m",v.local_zero_m);const r=await fetch("/datasets/files?"+params,{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:file});const data=await r.json();if(!r.ok)throw new Error(data.detail || "Upload failed");}
  await refresh();},"Source uploaded. Choose its processing action below.");
submit("process",async v=>{const payload={site_id:state.site,parcel_code:v.parcel_code,building_code:v.building_code};if($("processMode").value==="cloud"){if(!v.point_cloud_id)throw new Error("Choose a point cloud.");payload.point_cloud_id=v.point_cloud_id;}else{if(!v.dsm_id||!v.dtm_id)throw new Error("Choose both a DSM and a DTM.");payload.dsm_id=v.dsm_id;payload.dtm_id=v.dtm_id;}if(v.plan_dataset_id)payload.plan_dataset_id=v.plan_dataset_id;if(v.storeys)payload.storeys=Number(v.storeys);const result=await api("/process/building",payload);await refresh();lines($("processingResult"),[["Run",result.run_id],["Height",result.metrics.height_m+" m"],["Assumptions",result.metrics.assumptions.join("; ")]]);},"Processing complete. Inspect source assumptions and review the proposals.");
submit("partyForm",async(v,f)=>{const p=await api("/parties",v);await directories();$("party").value=p.id;f.reset();},"Party created.");
submit("baForm",async(v,f)=>{const b=await api("/baunits",v);await directories();$("baunit").value=b.id;f.reset();},"Administrative unit created.");
submit("reviewForm",async(v,f)=>{await api(scoped("/spatial-units/"+encodeURIComponent(state.code)+"/review"),{...v,release_review_block:f.elements.release_review_block.checked});await refresh();},"Review saved. Inspect the updated validation status before issuance.");
submit("rightsForm",async v=>{const payload={...v,site_id:state.site,spatial_unit_id:state.record.uuid};if(v.share!=="")payload.share=Number(v.share);else delete payload.share;await api("/rrr",payload);await selectUnit(state.record.uuid);},"Claim recorded with its evidence reference.");
submit("withdrawForm",async v=>{const id=state.record.uuid;await api(scoped("/units/"+encodeURIComponent(state.code)+"/withdraw"),v);await refresh();await selectUnit(id);},"Property withdrawn. Its historical record is preserved.");
button("issue",async()=>{await api(scoped("/issue/"+encodeURIComponent(state.code)),{});await refresh();},"Proposed ID issued. This is not an official DoLR identifier.");
button("version",async()=>{await api(scoped("/units/"+encodeURIComponent(state.code)+"/new-version"),{});await refresh();},"New version created. Issuance remains an explicit step.");
button("export",()=>download(scoped("/export/geojson"),"validated-properties.geojson"),"Validated site footprints downloaded.");
button("citygml",()=>download(scoped("/export/citygml?building_id="+state.record.uuid),"building-lod1.gml"),"Physical building envelope downloaded.");
button("validate",async()=>{const result=await api("/validate",{});await refresh();const ids=new Set(state.units.map(u=>u.uuid));const findings=result.findings.filter(f=>!f.passed && ids.has(f.spatial_unit_id));list("findings",findings,(li,f)=>{const unit=state.units.find(u=>u.uuid===f.spatial_unit_id);li.textContent=(unit?.local_code || "Property")+" · "+f.rule_code+" · "+JSON.stringify(f.detail);},"No failed geometry checks for this site. Review blocks may still prevent issuance.");},"Validation finished. Findings are filtered to the active site.");
initMap();action(async()=>{await loadSites();await directories();notice("Choose or create a site. The synthetic demo is available separately.");});
