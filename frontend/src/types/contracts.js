/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean,stall:string,superseded:boolean,rejection:?Object}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{date:string,weekday:string,configured:boolean,capacity:number,occupied:number,remaining:number,plans:Array<{job_id:number,job:string,stall:string,portions:number,current:boolean}>}} CapacityDay */
export {};
