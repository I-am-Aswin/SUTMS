// main.js - fetches backend endpoints and renders charts/tables

let updateInterval; // Variable to store the interval ID

// Function to update ntop stats
async function updateNtopStats() {
  try {
    const response = await fetch("/api/ntop/health");
    const data = await response.json();
    console.log("Received ntop health data:", data);

    if (!data.error) {
      // Update CPU info
      const cpu = data.cpu || {};
      document.getElementById("ntop-cpu").innerText = `${cpu.cpu_load ? cpu.cpu_load.toFixed(1) : '0'}% (User: ${cpu.cpu_user ? cpu.cpu_user.toFixed(1) : '0'}%, System: ${cpu.cpu_system ? cpu.cpu_system.toFixed(1) : '0'}%)`;
      
      // Update Memory info
      const mem = data.memory || {};
      document.getElementById("ntop-memory").innerText = 
        `${mem.mem_used_MB ? mem.mem_used_MB.toFixed(0) : '0'} MB / ${mem.mem_total_MB ? mem.mem_total_MB.toFixed(0) : '0'} MB`;
      
      // Update Storage info
      const storage = data.storage || {};
      document.getElementById("ntop-storage").innerText = 
        `${storage.storage_total_MB ? (storage.storage_total_MB/1024).toFixed(1) : '0'} GB`;
      
      // Update Alerts info
      const alerts = data.alerts || {};
      document.getElementById("ntop-alerts").innerText = 
        `${alerts.written_alerts || 0} written, ${alerts.dropped_alerts || 0} dropped`;
    } else {
      console.warn("Error in ntop health data:", data.error);
      document.getElementById("ntop-cpu").innerText = "Error";
      document.getElementById("ntop-memory").innerText = "Error";
      document.getElementById("ntop-storage").innerText = "Error";
      document.getElementById("ntop-alerts").innerText = "Error";
    }
  } catch (e) {
    console.error("Failed to fetch ntop health stats:", e);
  }
}

// Utility function to format bytes into human readable format
function formatBytes(bytes, decimals = 2) {
    if (!bytes) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}
async function SUTMS_init(){
  try {
    // Initial load
    await loadSummary();
    if(window.SUTMS_PAGE === "dashboard") {
      await renderTrafficChart();
      await loadAlertsTable("#alerts-table tbody");
      
      // Start auto-refresh for ntop stats
      updateInterval = setInterval(async () => {
        await updateNtopStats();
      }, 60000); // Update every minute (60000 ms)
    } else if(window.SUTMS_PAGE === "threats") {
      await loadAlertsTable("#tm-alerts-table tbody");
      loadIocInfo();
    } else if(window.SUTMS_PAGE === "analytics") {
      renderAnomalyChart();
      renderPerfChart();
    }
  } catch(e){
    console.error("Init error", e);
  }
}

async function loadSummary(){
  const res = await fetch("/api/suricata/alerts");
  const data = await res.json();
  const alerts = data.alerts||[];
  document.getElementById("card-threats")?.innerText = alerts.length;
  // devices approx: top_talkers length
  const ntop = await fetch("/api/ntop/traffic").then(r=>r.json()).catch(()=>({top_talkers:[]}))
  const devs = (ntop.top_talkers||[]).length;
  document.getElementById("card-devices")?.innerText = devs;
  // system health
  const sys = await fetch("/api/system/stats").then(r=>r.json()).catch(()=>({
    cpu: {temperature: 0, frequency: 0, percent: 0, cores: 0},
    memory: {percent: 0, used: 0, total: 0, swap_percent: 0},
    disk: {percent: 0, used: 0, total: 0}
  }));

  // Update CPU temperature and usage
  document.getElementById("cpu-temp").innerText = `${sys.cpu.temperature.toFixed(1)}`;
  document.getElementById("cpu-usage").innerText = `${sys.cpu.percent.toFixed(1)}%`;
  document.getElementById("cpu-freq").innerText = `${sys.cpu.frequency} MHz`;

  // Update memory information
  document.getElementById("memory-usage").innerText = `${sys.memory.percent.toFixed(1)}%`;
  document.getElementById("memory-used").innerText = `${formatBytes(sys.memory.used)} / ${formatBytes(sys.memory.total)}`;
  document.getElementById("swap-used").innerText = `${sys.memory.swap_percent.toFixed(1)}%`;

  // Update disk information
  document.getElementById("disk-usage").innerText = `${sys.disk.percent.toFixed(1)}%`;
  const diskFree = sys.disk.total - sys.disk.used;
  document.getElementById("disk-free").innerText = formatBytes(diskFree);

  // Update ntop health stats
  await updateNtopStats();
  }

async function renderTrafficChart(){
  const ctx = document.getElementById("trafficChart");
  if(!ctx) return;
  const payload = await fetch("/api/ntop/traffic").then(r=>r.json()).catch(()=>({traffic_timeseries:{labels:[],incoming:[],outgoing:[]}}));
  const ts = payload.traffic_timeseries || {labels: ["00:00"], incoming: [0], outgoing: [0]};
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: ts.labels,
      datasets: [
        {label:'Incoming (MB/s)', data: ts.incoming, borderColor:'#33b5e5', fill:false},
        {label:'Outgoing (MB/s)', data: ts.outgoing, borderColor:'#ffbb33', fill:false}
      ]
    },
    options: {plugins:{legend:{labels:{color:'#eaeaea'}}},scales:{x:{ticks:{color:'#aaa'},grid:{color:'#333'}},y:{ticks:{color:'#aaa'},grid:{color:'#333'}}}}
  });
}

async function loadAlertsTable(tbodySelector){
  const res = await fetch("/api/suricata/alerts");
  const data = await res.json();
  const alerts = data.alerts || [];
  const tbody = document.querySelector(tbodySelector);
  if(!tbody) return;
  tbody.innerHTML = "";
  for (let a of alerts){
    const tr = document.createElement("tr");
    const t = new Date(a.timestamp||"");
    tr.innerHTML = `<td>${t.toLocaleString()}</td><td>${a.src_ip||"-"}</td><td>${a.dest_ip||"-"}</td><td>${a.alert||a.event_type||"-"}</td><td>${a.severity||"-"}</td>`;
    tbody.appendChild(tr);
  }
}

async function loadIocInfo(){
  // placeholder: if you later add an endpoint to return IoC feed info, fetch and display it
  const el = document.getElementById("ioc-info");
  if(el) el.innerText = JSON.stringify({status:"configured", ntop: window.location.origin}, null, 2);
}

function renderAnomalyChart(){
  const ctx = document.getElementById("anomalyChart");
  if(!ctx) return;
  new Chart(ctx, {type:"bar",data:{labels:["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],datasets:[{label:"Anomalies",data:[3,5,2,6,4,1,3],backgroundColor:'#33b5e5'}]},options:{plugins:{legend:{labels:{color:'#eaeaea'}}},scales:{x:{ticks:{color:'#aaa'}},y:{ticks:{color:'#aaa'}}}});
}

function renderPerfChart(){
  const ctx = document.getElementById("perfChart");
  if(!ctx) return;
  fetch("/api/system/stats").then(r=>r.json()).then(sys=>{
    new Chart(ctx,{type:"line",data:{labels:["now"],datasets:[{label:"CPU %",data:[sys.cpu_percent],borderColor:'#33b5e5',fill:false},{label:"Mem %",data:[sys.mem_percent],borderColor:'#ffbb33',fill:false}]},options:{plugins:{legend:{labels:{color:'#eaeaea'}}},scales:{x:{ticks:{color:'#aaa'}},y:{ticks:{color:'#aaa'}}}});
  });
}
