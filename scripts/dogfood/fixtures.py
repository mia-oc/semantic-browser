"""Deterministic local fixtures for classically hard browser patterns.

Served from two origins so the cross-origin iframe is *really* cross-origin:
  main:  http://127.0.0.1:<port>/<name>
  other: http://localhost:<port2>/frame/<name>

Every page writes its outcome to ``document.title`` or ``#outcome`` so the harness
can check success without trusting the browser layer under test.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STYLE = "<style>body{font-family:sans-serif;margin:24px} .card{border:1px solid #ccc;padding:8px;margin:6px;display:inline-block;width:160px}</style>"


def _page(title: str, body: str, script: str = "") -> str:
    return f"<!doctype html><html><head><meta charset=utf-8><title>{title}</title>{STYLE}</head><body>{body}<script>{script}</script></body></html>"


PRODUCTS = ["Red Kettle", "Green Toaster", "Yellow Blender", "Blue Mug", "Black Pan", "White Bowl"]

SHOP = _page(
    "Shop",
    "<h1>Kitchen shop</h1><div id=grid>"
    + "".join(
        f'<div class=card><h3>{p}</h3><p>£{10 + i * 3}.99</p><button onclick="add(\'{p}\')">Add to basket</button></div>'
        for i, p in enumerate(PRODUCTS)
    )
    + "</div><h2>Basket</h2><ul id=basket></ul><div id=outcome></div>",
    "function add(p){var li=document.createElement('li');li.textContent=p;document.getElementById('basket').appendChild(li);"
    "document.getElementById('outcome').textContent='basket:'+Array.from(document.querySelectorAll('#basket li')).map(x=>x.textContent).join(',');"
    "document.title='basket:'+Array.from(document.querySelectorAll('#basket li')).map(x=>x.textContent).join(',');}",
)

COOKIE = _page(
    "Acme",
    '<nav><a href="/cookie_pricing">Pricing</a> <a href="/cookie_about">About</a></nav><h1>Acme Corp</h1><p>We make anvils.</p>'
    '<div id=consent style="position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center">'
    '<div style="background:#fff;padding:24px"><h2>We value your privacy</h2><p>We use cookies to improve your experience.</p>'
    '<button id=acc onclick="document.getElementById(\'consent\').remove()">Accept all cookies</button> '
    '<button>Manage preferences</button></div></div>',
)
COOKIE_PRICING = _page("Pricing", "<h1>Pricing</h1><p>Anvil: £99</p>")

SHADOW = _page(
    "Shadow login",
    "<h1>Portal</h1><login-box></login-box><div id=outcome></div>",
    """
class LoginBox extends HTMLElement{
 constructor(){super();const r=this.attachShadow({mode:'open'});
 r.innerHTML=`<form><label>Username <input name=u id=u></label><label>Password <input type=password name=p></label>
 <my-btn>Sign in</my-btn></form>`;
 r.querySelector('my-btn').addEventListener('click',()=>{
   const u=r.querySelector('#u').value;document.title='welcome:'+u;document.getElementById('outcome').textContent='welcome:'+u;});}
}
class MyBtn extends HTMLElement{connectedCallback(){this.style.cursor='pointer';this.style.border='1px solid #333';this.style.padding='4px';this.setAttribute('role','button');this.tabIndex=0;}}
customElements.define('my-btn',MyBtn);customElements.define('login-box',LoginBox);
""",
)

IFRAME_MAIN = _page(
    "Checkout",
    '<h1>Checkout</h1><p>Total: £42.00</p><iframe id=pay src="http://localhost:{PORT2}/frame/pay" width=420 height=220 title="Secure payment"></iframe>'
    "<div id=outcome></div>",
    "window.addEventListener('message',e=>{document.title='paid:'+e.data;document.getElementById('outcome').textContent='paid:'+e.data;});",
)
IFRAME_PAY = _page(
    "pay",
    '<form onsubmit="event.preventDefault();parent.postMessage(document.getElementById(\'card\').value,\'*\')">'
    '<label>Card number <input id=card name=card placeholder="1234 5678 9012 3456"></label> <button type=submit>Pay now</button></form>',
)

DROPDOWN = _page(
    "Trip planner",
    """<h1>Plan a trip</h1>
<label id=lbl>Destination</label>
<div id=combo role=combobox aria-labelledby=lbl aria-expanded=false tabindex=0 style="border:1px solid #333;width:200px;padding:4px">Choose...</div>
<ul id=list role=listbox style="display:none;list-style:none;border:1px solid #999;width:200px;padding:0">
 <li role=option>London</li><li role=option>Paris</li><li role=option>Rome</li></ul>
<h2>Date</h2><div id=cal style="display:grid;grid-template-columns:repeat(7,32px)"></div>
<button id=go>Search trips</button><div id=outcome></div>""",
    """
var sel={d:null,day:null};
var combo=document.getElementById('combo'),list=document.getElementById('list');
combo.onclick=()=>{list.style.display='block';combo.setAttribute('aria-expanded','true');};
list.querySelectorAll('li').forEach(li=>li.onclick=()=>{sel.d=li.textContent;combo.textContent=li.textContent;list.style.display='none';combo.setAttribute('aria-expanded','false');});
var cal=document.getElementById('cal');
for(let d=1;d<=28;d++){const c=document.createElement('div');c.textContent=d;c.style.cssText='cursor:pointer;text-align:center;border:1px solid #eee';c.onclick=()=>{sel.day=d;};cal.appendChild(c);}
document.getElementById('go').onclick=()=>{var t='trip:'+sel.d+':'+sel.day;document.title=t;document.getElementById('outcome').textContent=t;};
""",
)

SPA = _page(
    "SPA",
    '<nav><a href="/spa/home" data-r=home>Home</a> <a href="/spa/reports" data-r=reports>Reports</a> <a href="/spa/settings" data-r=settings>Settings</a></nav><main id=view></main>',
    """
function render(path){var v=document.getElementById('view');v.innerHTML='<p>Loading...</p>';
 setTimeout(()=>{var name=path.split('/').pop()||'home';
  v.innerHTML='<h1>'+name+' page</h1>'+(name==='settings'?'<label>Display name <input id=dn></label><button id=save>Save settings</button>':'<p>Content of '+name+'</p>');
  document.title='spa:'+name;
  var s=document.getElementById('save');if(s)s.onclick=()=>{document.title='saved:'+document.getElementById('dn').value;};
 },700);}
document.querySelectorAll('nav a').forEach(a=>a.onclick=e=>{e.preventDefault();history.pushState({},'',a.getAttribute('href'));render(location.pathname);});
render(location.pathname);
""",
)

SEARCH = _page(
    "Catalogue search",
    '<h1>Catalogue</h1><form id=f><input type=search id=q placeholder="Search catalogue" aria-label="Search catalogue"><button type=submit>Search</button></form><div id=results></div>',
    """
var DB=[['Anvil Classic','£49.99','In stock'],['Anvil Pro','£89.50','Low stock'],['Anvil Mini','£24.99','In stock'],['Hammer','£12.00','Out of stock']];
document.getElementById('f').onsubmit=e=>{e.preventDefault();var q=document.getElementById('q').value.toLowerCase();var r=document.getElementById('results');r.innerHTML='Searching...';
 setTimeout(()=>{r.innerHTML='<ul>'+DB.filter(x=>x[0].toLowerCase().includes(q)).map(x=>'<li><a href="/search_item?n='+encodeURIComponent(x[0])+'">'+x[0]+'</a> <span>'+x[1]+'</span> <em>'+x[2]+'</em></li>').join('')+'</ul>';document.title='results:'+q;},300);};
""",
)
SEARCH_ITEM = _page("Item", "<h1>Item detail</h1><p>Thanks for choosing.</p><div id=outcome>item-opened</div>", "document.title='item-opened'")

CAPTCHA = _page(
    "Verify you are human",
    """<h1>Security check</h1><div id=cap style="border:1px solid #888;padding:8px;width:330px">
<p id=prompt><b>Select all squares with a red circle</b></p>
<div id=grid style="display:grid;grid-template-columns:repeat(3,100px);gap:2px"></div>
<button id=verify>Verify</button></div><div id=outcome></div>
<img alt="captcha" src="/captcha.svg" id=txtcap style="display:none">""",
    """
var truth=[0,4,8];var picked=new Set();var g=document.getElementById('grid');
for(let i=0;i<9;i++){const t=document.createElement('div');t.className='tile';t.style.cssText='width:100px;height:100px;background:#eef;cursor:pointer;position:relative';
 t.innerHTML='<svg width="100" height="100"><'+(truth.includes(i)?'circle cx="50" cy="50" r="30" fill="red"':'rect x="20" y="20" width="60" height="60" fill="blue"')+'/></svg>';
 t.onclick=()=>{if(picked.has(i)){picked.delete(i);t.style.outline='none';}else{picked.add(i);t.style.outline='3px solid #0a0';}};g.appendChild(t);}
document.getElementById('verify').onclick=()=>{var ok=truth.length===picked.size&&truth.every(x=>picked.has(x));document.title=ok?'captcha-solved':'captcha-failed';document.getElementById('outcome').textContent=document.title;};
""",
)

CAPTCHA_DYNAMIC = _page(
    "Verify you are human",
    """<h1>Security check</h1><div id=cap style="border:1px solid #888;padding:8px;width:330px">
<p id=prompt><b>Select all squares with a red circle. Click verify once there are none left.</b></p>
<div id=grid style="display:grid;grid-template-columns:repeat(3,100px);gap:2px"></div>
<button id=verify>Verify</button></div><div id=outcome></div>""",
    """
var picked=new Set();var g=document.getElementById('grid');
function draw(t,i){t.dataset.gen=(+t.dataset.gen||0)+(t.dataset.init?1:0);t.dataset.init=1;t.style.outline='none';
 t.innerHTML='<svg width="100" height="100"><'+((+t.dataset.gen)%2===0&&i%2===0?'circle cx="50" cy="50" r="30" fill="red"':'rect x="20" y="20" width="60" height="60" fill="blue"')+'/></svg>';}
for(let i=0;i<9;i++){const t=document.createElement('div');t.className='tile';t.style.cssText='width:100px;height:100px;background:#eef;cursor:pointer';
 draw(t,i);t.onclick=()=>{if(picked.has(i)){picked.delete(i);t.style.outline='none';}else{picked.add(i);t.style.outline='3px solid #0a0';}};g.appendChild(t);}
document.getElementById('verify').onclick=()=>{var sel=[...picked];setTimeout(()=>{sel.forEach(i=>{picked.delete(i);draw(g.children[i],i);});},1000);};
""",
)

LAZY = _page(
    "Feed",
    '<h1>Activity feed</h1><div id=feed></div><div id=sentinel style="height:10px"></div><div id=outcome></div>',
    """
var n=0;function more(){for(let i=0;i<10;i++){n++;var d=document.createElement('div');d.style.cssText='height:60px;border-bottom:1px solid #ddd';
 d.innerHTML='Item '+n+' <button onclick="document.title=\\'opened:'+n+'\\'">Open item '+n+'</button>';document.getElementById('feed').appendChild(d);}}
more();new IntersectionObserver(es=>{if(es[0].isIntersecting&&n<60)more();}).observe(document.getElementById('sentinel'));
""",
)

HOVER = _page(
    "Hover menu",
    """<style>.m ul{display:none;position:absolute;background:#fff;border:1px solid #333;list-style:none;padding:4px;margin:0}.m:hover ul{display:block}</style>
<h1>Corp site</h1><div class=m style="display:inline-block"><span tabindex=0 style="cursor:pointer">Products ▾</span><ul><li><a href="/hover_target">Anvils</a></li><li><a href="/hover_x">Hammers</a></li></ul></div><div id=outcome></div>""",
)
HOVER_TARGET = _page("Anvils", "<h1>Anvils</h1><div id=outcome>anvils-page</div>", "document.title='anvils-page'")

CARDS = _page(
    "Cards",
    """<h1>Shop</h1><a href="/cart_page">Cart, 2 items</a><div class=grid>
<div class=card><a href="/p/1"><img alt="Sauce Backpack"></a><a href="/p/1" role=button><div class=name>Sauce Backpack</div></a><div class=desc>carry all the things with this sleek pack</div><div>$29.99</div><button>Add to cart</button></div>
<div class=card><a href="/p/2"><img alt="Bike Light"></a><a href="/p/2"><div class=name>Bike Light</div></a><div class=desc>a red light is not the desired state</div><div>$9.99</div><button>Add to cart</button></div>
<div class=card><a href="/p/3"><img alt="Bolt T-Shirt"></a><a href="/p/3"><div class=name>Bolt T-Shirt</div></a><div class=desc>get your testing superhero on</div><div>$15.99</div><button>Add to cart</button></div>
</div>""",
)

HUNG_SCRIPT = (
    "<!doctype html><title>Hung script</title><h1>Dynamic loading</h1><button id=go onclick=\"document.getElementById('out').textContent='Hello World!'\">Start</button>"
    "<div id=out></div><script src=\"/hang.js\"></script><p>after the script</p>"
)  # the heroku "the-internet" pattern: HTML is instant, a blocking script never arrives, DOMContentLoaded never fires
HUNG_HEAD = (
    "<!doctype html><html><head><title>Hung head</title><script src=\"/hang.js\"></script></head><body><h1>Dynamic loading</h1>"
    "<button id=go onclick=\"document.getElementById('out').textContent='Hello World!'\">Start</button><div id=out></div></body></html>"
)  # worse: the stalled script is in <head>, so the parser never reaches <body> until it arrives
FLAKY_HEAD = (
    "<!doctype html><html><head><title>Flaky head</title><script src=\"/flaky.js\"></script></head><body><h1>Flaky asset</h1>"
    "<button id=go>Start</button><div id=out></div><script>document.getElementById('go').onclick=function(){"
    "document.getElementById('out').textContent = window.flaky ? 'Hello World!' : 'broken: flaky.js missing'}</script></body></html>"
)  # the blocking script hangs on its FIRST request only (a jammed connection pool); an individual retry succeeds
FLAKY_HITS = {"n": 0}
HANG = threading.Event()  # released by FixtureServer.stop() so the hanging handler thread ends

CONTROLS = _page(
    "Controls",
    """<h1>Controls</h1>
<label>Volume <input type=range id=vol min=0 max=10 value=3 oninput="out.textContent='volume:'+this.value"></label>
<label>Upload <input type=file id=f multiple onchange="out.textContent='file:'+Array.from(this.files).map(x=>x.name).join(',')"></label>
<p><button id=dbl ondblclick="out.textContent='double-clicked'">Edit item</button></p>
<div id=ctx tabindex=0 oncontextmenu="event.preventDefault();out.textContent='context-menu'" style="border:1px solid;padding:8px;width:200px">Right-click area</div>
<ul><li draggable=true ondragstart="event.dataTransfer.setData('t','Alpha')">Alpha</li><li draggable=true ondragstart="event.dataTransfer.setData('t','Beta')">Beta</li></ul>
<div id=zone ondragover="event.preventDefault()" ondrop="event.preventDefault();out.textContent='dropped:'+event.dataTransfer.getData('t')" style="border:2px dashed #888;padding:20px;width:200px">Drop zone</div>
<div id=outcome></div>""",
    "var out=document.getElementById('outcome');",
)

BARE_LABELS = _page(
    "Bare labels",
    """<h1>Preferences</h1>
<form><p>Pick a snack:<br>
<input type=radio id=r1 name=snack value=c>Cheese<br>
<input type=radio id=r2 name=snack value=p>Peas<br>
<input type=radio id=r3 name=snack value=x checked>Cheese and peas<br></p>
<p><input type=checkbox name=nl><span>Subscribe to the newsletter</span> <input type=checkbox name=terms> I accept the terms</p></form>
<ul><li><div class=view><input type=checkbox class=toggle><label>buy milk</label><button class=destroy aria-label="Delete todo">x</button></div></li></ul>""",
)

MODAL_HEADER = _page(
    "Modal in header",
    """<header><nav><a href="/m1">Docs</a> <a href="/m2">Blog</a> <button id=open>Search the site</button></nav>
<my-search></my-search></header><main><h1>Docs home</h1><p>Welcome to the documentation.</p><a href="/m3">Getting started</a> <button>Search</button></main>
<script>customElements.define('my-search', class extends HTMLElement{constructor(){super();const r=this.attachShadow({mode:'open'});
r.innerHTML='<dialog style="width:300px;height:40px;top:20px"><form method=dialog><input type=search placeholder="Search" aria-label="Search"></form></dialog>';this.d=r.querySelector('dialog');}});
document.getElementById('open').onclick=()=>document.querySelector('my-search').d.showModal();</script>""",
)

ADS = _page(
    "News with ads",
    """<h1>Top story</h1><p>Real content here.</p>
<iframe title="3rd party ad content" width=300 height=250 src="/ad_frame"></iframe>
<iframe title="Payment form" width=300 height=120 src="/ad_frame_pay"></iframe>
<a href="/story2">Second story</a>""",
)
AD_FRAME = _page("ad", '<a href="https://adclick.g.doubleclick.net/pcs/click?x=1"><img alt=""></a><p>Buy now!</p>')
AD_FRAME_PAY = _page("pay", '<label>Card number <input name=cc></label>')

CAPTCHA_DRAG = _page(
    "Verify you are human",
    """<h1>Security check</h1><div id=cap-box style="border:1px solid #888;padding:10px;width:320px;margin-left:40px">
<p class=prompt-text>Drag the puzzle piece into the gap</p><canvas id=captcha-canvas width=300 height=160 style="border:1px solid #444"></canvas><div id=err style="display:none;color:#c00;font-size:12px">Please try again.</div>
<div style="opacity:0"><span>Please try again. (faded out by the parent)</span></div><div style="transform:scale(0)"><span>Incorrect, try again</span></div><div style="position:absolute;left:-9999px"><span>Wrong answer</span></div></div><div id=outcome></div>""",
    """
var c=document.getElementById('captcha-canvas'),x=c.getContext('2d'),piece={x:20,y:60,w:40,h:40},gap={x:210,y:60,w:40,h:40},drag=null;
function draw(){x.clearRect(0,0,300,160);x.fillStyle='#dde';x.fillRect(0,0,300,160);x.strokeStyle='#000';x.setLineDash([4,3]);x.strokeRect(gap.x,gap.y,gap.w,gap.h);
 x.setLineDash([]);x.fillStyle='#f80';x.fillRect(piece.x,piece.y,piece.w,piece.h);}
function pt(e){var r=c.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};}
c.addEventListener('mousedown',e=>{var p=pt(e);if(p.x>=piece.x&&p.x<=piece.x+piece.w&&p.y>=piece.y&&p.y<=piece.y+piece.h)drag={dx:p.x-piece.x,dy:p.y-piece.y};});
window.addEventListener('mousemove',e=>{if(!drag)return;var p=pt(e);piece.x=p.x-drag.dx;piece.y=p.y-drag.dy;draw();});
window.addEventListener('mouseup',()=>{if(!drag)return;drag=null;var ok=Math.abs(piece.x-gap.x)<14&&Math.abs(piece.y-gap.y)<14;document.title=ok?'captcha-solved':'captcha-failed';document.getElementById('outcome').textContent=document.title;document.getElementById('err').style.display=ok?'none':'block';if(!ok){piece.x=20;piece.y=60;draw();}});
draw();""",
)

CAPTCHA_CLICK = _page(
    "Verify you are human",
    """<h1>Security check</h1><div id=cap-box style="border:1px solid #888;padding:10px;width:320px">
<p class=prompt-text>Click on every red square</p><canvas id=captcha-canvas width=300 height=160 style="border:1px solid #444"></canvas></div><div id=outcome></div>""",
    """
var c=document.getElementById('captcha-canvas'),x=c.getContext('2d'),red=[{x:30,y:30},{x:220,y:100}],blue=[{x:120,y:40},{x:150,y:110}],got=new Set(),bad=false;
x.fillStyle='#eee';x.fillRect(0,0,300,160);red.forEach(r=>{x.fillStyle='#d00';x.fillRect(r.x,r.y,40,40);});blue.forEach(r=>{x.fillStyle='#00d';x.fillRect(r.x,r.y,40,40);});
c.addEventListener('click',e=>{var r=c.getBoundingClientRect(),px=e.clientX-r.left,py=e.clientY-r.top,hit=false;
 red.forEach((q,i)=>{if(px>=q.x&&px<=q.x+40&&py>=q.y&&py<=q.y+40){got.add(i);hit=true;}});if(!hit)bad=true;
 document.title=(!bad&&got.size===red.length)?'captcha-solved':(bad?'captcha-failed':'captcha-partial');document.getElementById('outcome').textContent=document.title;});
""",
)

CAPTCHA_TEXT = _page(
    "Retype the characters",
    """<h1>Demo form</h1><p>Retype the characters from the picture:</p>
<img alt="captcha" id=cap-img width=160 height=50 src="data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='50'%3E%3Crect width='160' height='50' fill='%23ddd'/%3E%3Ctext x='20' y='36' font-size='30' font-family='Arial'%3EQ7ZP%3C/text%3E%3C/svg%3E">
<p><input type=text name=captchaCode id=captchaCode aria-label="Retype the characters from the picture:"> <input type=button id=v value="Validate"></p><div id=outcome></div>""",
    "document.getElementById('v').onclick=()=>{var ok=document.getElementById('captchaCode').value.toUpperCase()==='Q7ZP';document.title=ok?'captcha-solved':'captcha-failed';document.getElementById('outcome').textContent=ok?'Correct!':'Incorrect, please try again';};",
)

PAGES = {
    "/captcha_text": CAPTCHA_TEXT,
    "/captcha_drag": CAPTCHA_DRAG,
    "/captcha_click": CAPTCHA_CLICK,
    "/ads": ADS,
    "/ad_frame": AD_FRAME,
    "/ad_frame_pay": AD_FRAME_PAY,
    "/modal_header": MODAL_HEADER,
    "/bare_labels": BARE_LABELS,
    "/controls": CONTROLS,
    "/cards": CARDS,
    "/cart_page": _page("Your cart", "<h1>Your cart</h1><p>2 items</p>"),
    "/hung_script": HUNG_SCRIPT,
    "/hung_head": HUNG_HEAD,
    "/flaky_head": FLAKY_HEAD,
    "/shop": SHOP,
    "/cookie": COOKIE,
    "/cookie_pricing": COOKIE_PRICING,
    "/shadow": SHADOW,
    "/iframe": IFRAME_MAIN,
    "/dropdown": DROPDOWN,
    "/search": SEARCH,
    "/search_item": SEARCH_ITEM,
    "/captcha": CAPTCHA,
    "/captcha_dynamic": CAPTCHA_DYNAMIC,
    "/lazy": LAZY,
    "/hover": HOVER,
    "/hover_target": HOVER_TARGET,
}


class _Handler(BaseHTTPRequestHandler):
    port2 = 0

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/flaky.js":
            FLAKY_HITS["n"] += 1
            if FLAKY_HITS["n"] == 1:
                HANG.wait(30)
            data = b"window.flaky = 1;"
            self.send_response(200)
            self.send_header("content-type", "application/javascript")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/hang.js":
            HANG.wait(30)
            self.send_response(200)
            self.send_header("content-type", "application/javascript")
            self.end_headers()
            return
        if path.startswith("/frame/pay"):
            body = IFRAME_PAY
        elif path.startswith("/spa"):
            body = SPA
        else:
            body = PAGES.get(path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        body = body.replace("{PORT2}", str(self.port2))
        data = body.encode()
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FixtureServer:
    """Starts both origins on ephemeral ports."""

    def __init__(self) -> None:
        self.main = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.other = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        _Handler.port2 = self.other.server_address[1]
        self.base = f"http://127.0.0.1:{self.main.server_address[1]}"
        self._threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (self.main, self.other)]

    def start(self) -> FixtureServer:
        for t in self._threads:
            t.start()
        return self

    def stop(self) -> None:
        HANG.set()
        self.main.shutdown()
        self.other.shutdown()


if __name__ == "__main__":  # manual poking
    s = FixtureServer().start()
    print(s.base)
    threading.Event().wait()
