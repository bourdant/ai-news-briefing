
window.WORKER_URL = "https://ai-news-reactions.ammi88-05f.workers.dev";
function pickedKey(date, id){ return "reacted:" + date + ":" + id; }
async function sendReaction(date, id, reaction, btn){
  if(!window.WORKER_URL) return;
  var group = btn.closest(".reactions");
  try{
    var res = await fetch(window.WORKER_URL + "/react", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({date: date, id: id, reaction: reaction})
    });
    var data = await res.json();
    if(data && data.counts){ updateCounts(group, data.counts); }
    try{ localStorage.setItem(pickedKey(date, id), reaction); }catch(e){}
    Array.from(group.querySelectorAll("button")).forEach(function(b){
      b.classList.toggle("picked", b === btn);
    });
  }catch(e){ console.error("reaction send failed", e); }
}
function updateCounts(group, counts){
  Array.from(group.querySelectorAll("button")).forEach(function(b){
    var r = b.getAttribute("data-reaction");
    var span = b.querySelector(".count");
    if(span && counts[r] !== undefined){ span.textContent = counts[r]; }
  });
}
document.addEventListener("DOMContentLoaded", function(){
  document.querySelectorAll(".card").forEach(function(card){
    var date = card.getAttribute("data-date");
    var id = card.getAttribute("data-id");
    var group = card.querySelector(".reactions");
    if(!group) return;
    var picked = null;
    try{ picked = localStorage.getItem(pickedKey(date, id)); }catch(e){}
    if(picked){
      group.querySelectorAll("button").forEach(function(b){
        b.classList.toggle("picked", b.getAttribute("data-reaction") === picked);
      });
    }
    if(window.WORKER_URL){
      fetch(window.WORKER_URL + "/counts?date=" + encodeURIComponent(date) + "&id=" + encodeURIComponent(id))
        .then(function(r){ return r.json(); })
        .then(function(data){ if(data && data.counts) updateCounts(group, data.counts); })
        .catch(function(){});
    }
  });
});
