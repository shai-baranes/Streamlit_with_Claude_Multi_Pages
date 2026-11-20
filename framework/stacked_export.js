// Source rows stay in the file once. Views and pages refer back to those rows.
function renderStacked({parentElement: root, data}) {
  const {columns, rows, presets, pageSize} = data;
  const offset = name => columns.indexOf(name) + 1;
  const time = offset("Seconds");
  const fields = columns.filter(name => name !== "Seconds");
  const number = value => value == null || String(value).trim() === "" ? NaN : Number(value);
  const nullable = new Set(data.nullable);
  const ordered = rows.slice().sort((a,b) => {
    const x = number(a[time]), y = number(b[time]);
    return Number.isNaN(x) - Number.isNaN(y) || x-y;
  });
  let {selected, mode, exclusions, source, active} = data;
  let page = 0, sort = -1, direction = 1, notice = "";
  let events = [];
  function node(parent, tag, text) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    parent.append(el);
    return el;
  }
  function button(parent, label, action, disabled = false) {
    const el = node(parent, "button", label);
    el.disabled = disabled;
    el.onclick = action;
    return el;
  }
  function picker(parent, label, options, value, action) {
    const select = node(node(parent,"label",label+" "), "select");
    for (const [id,name] of options) select.add(new Option(name,id));
    select.value = value;
    select.onchange = () => action(select.value);
  }
  function update(manual = true) {
    if (manual) { active = null; notice = ""; }
    exclusions = exclusions.filter(c => selected.includes(c)).slice(0, Math.max(0,selected.length-1));
    sort = -1;
    page = 0;
    events = [];
    const compare = (mode === "Stacked by Left" ? selected.slice(0,1)
      : selected.filter(name => !exclusions.includes(name))).map(offset);
    let previousTime = NaN;
    if (selected.length) ordered.forEach((row,i) => {
      if (mode !== "Full") {
        const changed = compare.some(col => {
          const previous = i ? ordered[i-1][col] : null;
          if (row[col] == null || previous == null) return !nullable.has(col);
          return row[col] !== previous;
        });
        if (!changed) return;
      }
      const seconds = number(row[time]);
      const scaled = (seconds - previousTime)*1000;
      const floor = Math.floor(scaled);
      // NumPy rounds exact half-way cases to the even integer.
      const rounded = scaled-floor === 0.5 ? floor + Math.abs(floor%2) : Math.round(scaled);
      const delta = events.length ? (Number.isFinite(rounded) ? rounded/1000 : null) : "-";
      events.push({row, delta});
      previousTime = seconds;
    });
    const index = events.findIndex(e => e.row[0] === source);
    if (index < 0) source = null;
    else page = Math.floor(index/pageSize);
    draw();
  }
  function apply(id) {
    const preset = presets.find(p => p.id === id);
    if (!preset) return;
    const available = preset.columns.filter(c => fields.includes(c));
    if (!available.length) { notice = "None of this preset’s display columns are loaded."; draw(); return; }
    selected = available;
    exclusions = preset.exclusions.filter(c => selected.includes(c)).slice(0,selected.length-1);
    const missing = preset.columns.filter(c => !available.includes(c));
    const omitted = preset.exclusions.filter(c => !exclusions.includes(c));
    notice = [missing.length && "Unavailable columns: "+missing.join(", "),
              omitted.length && "Omitted exclusions: "+omitted.join(", ")].filter(Boolean).join(". ");
    active = id;
    mode = preset.view_mode ?? mode;
    update(false);
  }
  function draw() {
    root.replaceChildren();
    node(root,"h2","Stacked event table");
    const controls = node(root,"div");
    controls.className = "stacked-controls";
    const choices = values => values.map(v => [v,v]);
    picker(controls,"Saved preset",[["","Choose a preset"],...presets.map(p=>[p.id,p.name])],active??"",apply);
    picker(controls,"View mode",choices(["Full","Stacked by Left","Stacked by All"]),mode,v=>{mode=v;update();});
    picker(controls,"Add column",[["","Choose a column"],...choices(fields.filter(c=>!selected.includes(c)))],"",v=>{
      if (v) {selected.push(v);update();}
    });
    selected.forEach((name,i)=>{
      const line = node(controls,"div",name + (i===0 ? " (anchor) " : " "));
      function move(step) {
        [selected[i],selected[i+step]] = [selected[i+step],selected[i]];
        update();
      }
      button(line,"Move up",()=>move(-1),i===0);
      button(line,"Move down",()=>move(1),i===selected.length-1);
      button(line,"Remove",()=>{selected.splice(i,1);update();});
      if (mode === "Stacked by All") {
        const label = node(line,"label","Exclude from change detection ");
        const box = node(label,"input");
        box.type = "checkbox"; box.checked = exclusions.includes(name);
        box.disabled = !box.checked && exclusions.length===selected.length-1;
        box.onchange = ()=>{exclusions=box.checked?[...exclusions,name]:exclusions.filter(c=>c!==name);update();};
      }
    });
    if (notice) node(root,"p",notice);
    if (!selected.length) {node(root,"p","Select a column to see event rows.");return;}
    const pages = Math.max(1,Math.ceil(events.length/pageSize));
    node(root,"p",events.length+" events / "+rows.length+" filtered rows · Page "+(page+1)+" of "+pages);
    button(root,"Previous",()=>{page--;draw();},page===0);
    button(root,"Next",()=>{page++;draw();},page+1>=pages);
    const scroll = node(root,"div"); scroll.className="stacked-scroll";
    const table=node(scroll,"table"), head=node(node(table,"thead"),"tr");
    const names=["Seconds","Dt [seconds]",...selected], positions=names.map(offset);
    function cell(event,i) {return i===1?event.delta:event.row[positions[i]];}
    names.forEach((name,i)=>button(node(head,"th"),name,()=>{
      direction=sort===i?-direction:1;sort=i;
      events.sort((a,b)=>{
        const x=cell(a,i), y=cell(b,i);
        if(x==null || y==null) return (x==null)-(y==null);
        const nx=number(x), ny=number(y);
        return direction*(Number.isFinite(nx)&&Number.isFinite(ny)?nx-ny:String(x).localeCompare(String(y)));
      });
      page=0;draw();
    }));
    const body=node(table,"tbody");
    for(const event of events.slice(page*pageSize,(page+1)*pageSize)){
      const tr=node(body,"tr");
      tr.tabIndex=0;tr.setAttribute("aria-selected",String(event.row[0]===source));
      tr.onclick=()=>{source=event.row[0];draw();};
      tr.onkeydown=e=>{if(e.key==="Enter")tr.click();};
      names.forEach((_,i)=>node(tr,"td",cell(event,i)));
    }
    const current=source===null?null:rows.find(r=>r[0]===source);
    if(current){
      node(root,"h3","Selected source row");
      const details=node(root,"dl");
      for(const name of ["Seconds",selected[0],...fields.filter(c=>c!==selected[0])]){
        node(details,"dt",name);node(details,"dd",current[offset(name)]);
      }
    }
  }
  update(false);
}
