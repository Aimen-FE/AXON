/* Manual local microphone capture. Samples stay in memory until the user stops. */
class AxonCapture extends AudioWorkletProcessor {
 constructor(){super();this.buffer=new Float32Array(4096);this.used=0;this.active=true;this.port.onmessage=e=>{if(e.data==='stop'){this.active=false;if(this.used)this.port.postMessage(this.buffer.slice(0,this.used))}}}
 process(inputs){if(!this.active)return false;const channel=inputs[0]?.[0];if(channel)for(const value of channel){this.buffer[this.used++]=value;if(this.used===this.buffer.length){this.port.postMessage(this.buffer);this.buffer=new Float32Array(4096);this.used=0}}return true}
}
registerProcessor('axon-manual-capture',AxonCapture);
