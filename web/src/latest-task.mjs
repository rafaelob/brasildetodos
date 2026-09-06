// SPDX-License-Identifier: AGPL-3.0-or-later
/** A per-component latest-operation gate. Cancel also invalidates non-abortable work. */
export function createLatestTask(){
  /** @type {AbortController | null} */
  let active=null;
  function cancel(){if(active){active.abort();active=null;}}
  /**
   * Publication callbacks must be synchronous. Only the active request may publish.
   * @template T
   * @param {(signal: AbortSignal) => Promise<T>} operation
   * @param {{success?: (value:T)=>void, failure?: (error:unknown)=>void, settled?:()=>void}} handlers
   * @returns {Promise<'completed'|'failed'|'superseded'>}
   */
  async function run(operation,handlers={}){
    cancel();const controller=new AbortController();active=controller;
    const current=()=>active===controller&&!controller.signal.aborted;
    try{
      const value=await operation(controller.signal);
      if(!current())return 'superseded';
      handlers.success?.(value);return 'completed';
    }catch(error){
      if(!current())return 'superseded';
      handlers.failure?.(error);return 'failed';
    }finally{
      if(current()){
        active=null;
        handlers.settled?.();
      }
    }
  }
  return {run,cancel};
}
