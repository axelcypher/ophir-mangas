// Reading the ISBN barcode on a volume's back: with the camera or from a photo (docs/adr/0003).
// The browser's own BarcodeDetector is used where there is one (Chrome on Android); everywhere else
// (Safari, Firefox) the small EAN-13 decoder below reads the frames. An ISBN barcode is an EAN-13
// starting with 978 or 979; the five-digit price add-on next to it is ignored.

// ---- EAN-13: from pixels to digits ---------------------------------------------------------------

// Bar widths in modules of each digit, space first (L and G on the left half, R = L on the right).
const EAN_L=['3211','2221','2122','1411','1132','1231','1114','1312','1213','3112'];
const EAN_G=['1123','1222','2212','1141','2311','1321','4111','2131','3121','2113'];
// Which digits of the left half use G: that pattern spells the first digit.
const EAN_PARITY=['LLLLLL','LLGLGG','LLGGLG','LLGGGL','LGLLGG','LGGLLG','LGGGLL','LGLGLG','LGLGGL','LGGLGL'];
const EAN_RUNS=59;              // start guard 3 + 6 digits x 4 + middle 5 + 6 x 4 + end guard 3
const EAN_DIGIT_ERROR=1.5;      // how far (in modules, summed) a digit's bars may be off its pattern

function ean13Valid(code){
  if(!/^\d{13}$/.test(code))return false;
  let sum=0;
  for(let i=0;i<12;i++)sum+=Number(code[i])*(i%2?3:1);
  return (10-sum%10)%10===Number(code[12]);
}
const isIsbnBarcode=code=>ean13Valid(code)&&/^97[89]/.test(code);

// Light and dark runs of one line of pixels (luminance 0-255), split at the middle of the line's
// darkest and lightest value over a sliding window, so a shadow across the cover does not merge bars.
function eanRuns(values){
  const runs=[],window=Math.max(16,Math.round(values.length/8));
  let dark=null;
  for(let i=0;i<values.length;i++){
    let low=255,high=0;
    for(let j=Math.max(0,i-window);j<Math.min(values.length,i+window);j++){if(values[j]<low)low=values[j];if(values[j]>high)high=values[j]}
    const isDark=high-low<24?false:values[i]<(low+high)/2;
    if(isDark===dark)runs[runs.length-1].width++;
    else{runs.push({dark:isDark,width:1});dark=isDark}
  }
  return runs;
}

function eanDigit(widths,patterns){
  const unit=widths.reduce((sum,width)=>sum+width,0)/7;
  let best=-1,error=Infinity;
  patterns.forEach((pattern,digit)=>{
    let off=0;
    for(let i=0;i<4;i++)off+=Math.abs(widths[i]/unit-Number(pattern[i]));
    if(off<error){error=off;best=digit}
  });
  return {digit:best,error};
}

// The code whose start guard is the dark run at `start`, or null.
function eanFromRuns(runs,start){
  if(start+EAN_RUNS>runs.length||!runs[start].dark)return null;
  const widths=runs.slice(start,start+EAN_RUNS).map(run=>run.width);
  const module=(widths[0]+widths[1]+widths[2])/3;
  if(start>0&&runs[start-1].width<module*3)return null;                      // the quiet zone before it
  const guard=values=>values.every(width=>width>module*0.4&&width<module*2.2);
  if(!guard(widths.slice(0,3))||!guard(widths.slice(27,32))||!guard(widths.slice(56,59)))return null;
  let digits='',parity='';
  for(let d=0;d<6;d++){
    const part=widths.slice(3+d*4,7+d*4),l=eanDigit(part,EAN_L),g=eanDigit(part,EAN_G);
    const best=l.error<=g.error?l:g;
    if(best.error>EAN_DIGIT_ERROR)return null;
    digits+=best.digit;parity+=l.error<=g.error?'L':'G';
  }
  for(let d=0;d<6;d++){
    const right=eanDigit(widths.slice(32+d*4,36+d*4),EAN_L);
    if(right.error>EAN_DIGIT_ERROR)return null;
    digits+=right.digit;
  }
  const first=EAN_PARITY.indexOf(parity);
  if(first<0)return null;
  const code=`${first}${digits}`;
  return ean13Valid(code)?code:null;
}

function eanFromLine(values){
  for(const line of [values,[...values].reverse()]){
    const runs=eanRuns(line);
    for(let i=0;i<runs.length;i++){const code=eanFromRuns(runs,i);if(code)return code}
  }
  return null;
}

// An EAN-13 in a picture ({data: RGBA bytes, width, height}, as a canvas gives it): tried along a
// number of lines across its middle, and down its columns for a barcode turned sideways.
function decodeEan13(image,{lines=24}={}){
  const {data,width,height}=image;
  const gray=x=>y=>{const i=(y*width+x)*4;return (data[i]*299+data[i+1]*587+data[i+2]*114)/1000};
  for(let k=0;k<lines;k++){
    const y=Math.round(height*(0.2+0.6*(lines===1?0.5:k/(lines-1))));
    const row=new Array(width);
    for(let x=0;x<width;x++)row[x]=gray(x)(y);
    const code=eanFromLine(row);
    if(code)return code;
  }
  for(let k=0;k<Math.ceil(lines/2);k++){
    const x=Math.round(width*(0.25+0.5*(k/Math.max(1,Math.ceil(lines/2)-1))));
    const column=new Array(height);
    for(let y=0;y<height;y++)column[y]=gray(x)(y);
    const code=eanFromLine(column);
    if(code)return code;
  }
  return null;
}

// ---- The scanner dialog --------------------------------------------------------------------------

const SCAN_INTERVAL_MS=180;
const SCAN_WIDTH=720;

async function detectorFor(){
  if(!('BarcodeDetector' in globalThis))return null;
  try{
    const formats=await BarcodeDetector.getSupportedFormats?.();
    if(formats&&!formats.includes('ean_13'))return null;
    return new BarcodeDetector({formats:['ean_13']});
  }catch{return null}
}

// Reads a code from what is drawable (a video frame, an image) with the detector or the decoder.
async function readBarcode(source,detector,canvas,{sourceWidth,sourceHeight}){
  if(detector){
    try{
      const found=await detector.detect(source);
      const code=found.map(item=>String(item.rawValue||'')).find(isIsbnBarcode);
      if(code)return code;
    }catch{}
  }
  if(!sourceWidth||!sourceHeight)return null;
  const scale=Math.min(1,SCAN_WIDTH/sourceWidth);
  canvas.width=Math.round(sourceWidth*scale);canvas.height=Math.round(sourceHeight*scale);
  const context=canvas.getContext('2d',{willReadFrequently:true});
  context.drawImage(source,0,0,canvas.width,canvas.height);
  const code=decodeEan13(context.getImageData(0,0,canvas.width,canvas.height));
  return code&&isIsbnBarcode(code)?code:null;
}

// The dialog: the camera's picture with a frame to hold the barcode in, a photo as the way for
// browsers without camera access, and typing the ISBN. onIsbn(code) gets the 13 digits.
function openScanner({onIsbn,title='ISBN scannen'}={}){
  const modal=openDialog({id:'scanner-dialog',eyebrow:'STRICHCODE',title,stack:true,
    intro:'Halte den Strichcode auf der Rückseite des Bands waagerecht in den Rahmen.',body:`
    <div class="mg-scanner"><video id="scanner-video" playsinline muted autoplay></video><span class="mg-scanner-frame" aria-hidden="true"></span>
      <p class="mg-scanner-status" id="scanner-status" aria-live="polite">Kamera wird gestartet …</p></div>
    <div class="mg-scanner-alternatives">
      <label class="secondary-button mg-file-button">Foto aufnehmen<input type="file" id="scanner-photo" accept="image/*" capture="environment"></label>
      <span class="mg-scanner-or">oder</span>
      <span class="mg-scanner-typed"><input class="dl-control" id="scanner-typed" inputmode="numeric" placeholder="ISBN eintippen" autocomplete="off"><button type="button" class="primary-button" id="scanner-use">Weiter</button></span>
    </div>
    <canvas id="scanner-canvas" hidden></canvas>`});
  const video=$('#scanner-video',modal),status=$('#scanner-status',modal),canvas=$('#scanner-canvas',modal);
  let stream=null,timer=null,done=false,detector=null;
  const stop=()=>{clearTimeout(timer);stream?.getTracks().forEach(track=>track.stop());stream=null};
  const finish=code=>{
    if(done)return;done=true;stop();
    navigator.vibrate?.(60);
    closeDialog();onIsbn?.(code);
  };
  // The dialog may be closed any way (×, Escape, a click outside): the camera goes off with it.
  const watcher=new MutationObserver(()=>{if(!document.body.contains(modal)){stop();watcher.disconnect()}});
  watcher.observe(document.body,{childList:true});
  const scan=async()=>{
    if(done||!stream)return;
    const code=await readBarcode(video,detector,canvas,{sourceWidth:video.videoWidth,sourceHeight:video.videoHeight});
    if(code){finish(code);return}
    timer=setTimeout(scan,SCAN_INTERVAL_MS);
  };
  (async()=>{
    detector=await detectorFor();
    if(!navigator.mediaDevices?.getUserMedia){status.textContent='Dieser Browser gibt die Kamera nicht frei – nimm ein Foto auf oder tippe die ISBN ein.';return}
    try{
      stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});
      if(done||!document.body.contains(modal)){stop();return}
      video.srcObject=stream;await video.play().catch(()=>{});
      status.textContent='Suche Strichcode …';
      scan();
    }catch(error){
      status.textContent=error?.name==='NotAllowedError'?'Kein Zugriff auf die Kamera erlaubt – nimm ein Foto auf oder tippe die ISBN ein.'
        :'Keine Kamera verfügbar – nimm ein Foto auf oder tippe die ISBN ein.';
    }
  })();
  $('#scanner-photo',modal).onchange=async event=>{
    const file=event.target.files[0];if(!file)return;
    status.textContent='Foto wird gelesen …';
    try{
      const bitmap=await createImageBitmap(file);
      const code=await readBarcode(bitmap,detector||await detectorFor(),canvas,{sourceWidth:bitmap.width,sourceHeight:bitmap.height});
      if(code)finish(code);
      else status.textContent='Im Foto war kein ISBN-Strichcode zu lesen. Näher heran, scharf und gerade halten – oder die ISBN eintippen.';
    }catch{status.textContent='Das Foto ließ sich nicht öffnen.'}
  };
  const typed=()=>{
    const digits=$('#scanner-typed',modal).value.replace(/[^\dXx]/g,'');
    if(digits.length!==10&&digits.length!==13){toast('Eine ISBN hat 10 oder 13 Ziffern.');return}
    finish(digits.toUpperCase());
  };
  $('#scanner-use',modal).onclick=typed;
  $('#scanner-typed',modal).addEventListener('keydown',event=>{if(event.key==='Enter')typed()});
}
