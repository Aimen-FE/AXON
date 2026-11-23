export interface Row { id:string; created_at:string; updated_at:string }
export type Role='student'|'teacher'|'admin';
export interface Preferences {theme:'light'|'dark'|'system';notifications:Record<string,boolean>;automatic_personal_actions:boolean;conversation_retention_days?:number|null}
export interface User extends Row {demo_teacher?:boolean;demo_expires_at?:string|null;temporary_guest?:boolean;guest_expires_at?:string|null;username:string;display_name:string;role:Role;is_demo:boolean;center_id:string;group_ids:string[];preferences:Preferences;active?:boolean;has_academic_profile?:boolean}
export interface Named extends Row {name:string}
export interface Subject extends Named {color:string}
export interface Teaching extends Row {teacher_id:string;group_id:string;subject_id:string}
export interface Academic {years:Named[];center:Named&{town:string;settings:{bathroom_retention_days:number;automation_enabled:boolean}};groups:(Named&{course_id:string})[];courses:Named[];subjects:Subject[];classrooms:Named[];teaching:Teaching[];teachers:{id:string;display_name:string}[]}
export interface Event extends Row {title:string;description:string;starts_at:string;ends_at:string;kind:string;group_id:string|null;subject_id:string|null;classroom_id:string|null;owner_id:string;visibility:string;status:string;source:string;version:number;syllabus:string;class_id?:string;activity_id?:string|null}
export interface Action extends Row {tool:string;arguments:Record<string,unknown>;status:string;result:Record<string,unknown>;expires_at:string}
export interface ToolResult {status:string;tool:string;action?:Action;result?:Record<string,unknown>;conflicts?:{title:string}[]}
export interface Message extends Row {role:'user'|'assistant';content:string;details:{engine?:string;error?:boolean;run_id?:string;run_status?:string;tools?:{name:string;status:string}[];citations?:{document_id?:string;title:string;location?:string;status:string;url?:string;checked_at?:string}[];actions?:Action[];event_ids?:string[]}}
export interface Conversation extends Row {title:string}
export interface Assignment extends Row {title:string;description:string;group_id:string;subject_id:string;due_at:string;material_ids:string[];submission:Submission|null;class_id?:string;class_status?:string}
export interface Submission extends Row {content:string;status:string;student_name?:string}
export interface Schedule extends Row {group_id:string;subject_id:string;teacher_id:string;classroom_id:string|null;weekday:number;starts:string;ends:string;source:string}
export interface Doc extends Row {title:string;filename:string;access:string;group_id:string|null;subject_id:string|null;version:number;status:string;size:number;source:string;owner_id:string}
export interface Chunk extends Row {content:string;location:string}
export interface SearchChunk {document_id:string;title:string;location:string;content:string;version:number;status:string}
export interface Memory extends Row {content:string;category:string;event_at:string|null;source:string;entity:string;conversation_id?:string}
export interface MemorySearch {memories:Memory[];messages:Memory[]}
export interface Notification extends Row {title:string;content:string;category:string;read:boolean}
export interface Bathroom extends Row {student_id:string;student_name:string;group_id:string;left_at:string;returned_at:string|null;correction_reason:string}
export interface Finding {id:string;kind:string;title:string;detail:string;status:string;correction:{tool:string;arguments:Record<string,unknown>}|null;action_id?:string}
export interface Report extends Row {findings:Finding[];trigger:string}
export interface Audit extends Row {operation:string;object_type:string;object_id:string;actor_id:string|null;details:Record<string,unknown>}
export interface System {full_demo?:boolean;public_demo?:boolean;remote_demo?:boolean;ai:{available:boolean;model:string;mode:string};internet:boolean;ocr:boolean;demo:boolean;voice:string}
export interface Dashboard {today_schedule_count?:number;personal_tasks?:{id:string;title:string;due_at:string;subject_id:string|null}[];events:Event[];assignments:Assignment[];pending_actions:Action[];unread_notifications:number}
