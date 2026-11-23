export type ClassRole = 'student' | 'teacher';
export type ClassColor = 'mint' | 'sky' | 'amber' | 'orchid' | 'coral';
export type ActivityKind = 'task' | 'exercise' | 'quiz' | 'project' | 'exam';
export type ActivityStatus = 'draft' | 'published' | 'closed';
export type WorkStatus = 'draft' | 'submitted' | 'returned';

export interface ClassRoom {
  id: string;
  name: string;
  description: string;
  group_id: string;
  subject_id: string;
  group: string;
  course: string;
  stage: string;
  course_id: string;
  subject: string;
  color: ClassColor;
  archived: boolean;
  can_manage: boolean;
  has_join_code: boolean;
  join_code?: string;
}

export interface ClassDirectory {
  classes: ClassRoom[];
  invitations: {id: string; name: string; subject: string; expires_at: string}[];
}

export interface ClassPost {
  id: string;
  title: string;
  content: string;
  author_name: string;
  author_id: string;
  created_at: string;
  pinned: boolean;
  comments_open: boolean;
}

export type ClassComment = Pick<ClassPost, 'id' | 'content' | 'author_name' | 'author_id' | 'created_at'>;
export interface ClassTopic {id: string; name: string}
export interface ClassFile {
  id: string;
  title: string;
  filename: string;
  size: number;
  topic_id: string | null;
  activity_id: string | null;
}
export interface ClassPeople {
  members: {id: string; name: string; role: ClassRole}[];
  teams: {id: string; name: string; students: string[]}[];
}

export interface WorkState {
  id: string;
  version: number;
  status: WorkStatus;
  submitted_at: string | null;
}
export interface ActivityRow {
  id: string;
  title: string;
  kind: ActivityKind;
  delivery: 'individual' | 'team';
  status: ActivityStatus;
  due_at: string | null;
  topic_id: string | null;
  locked: boolean;
  submission?: WorkState | null;
}
export interface ClassQuestion {prompt: string; options: string[]}
export interface RubricCriterion {title: string; description: string; points: number}
export interface ClassActivity extends ActivityRow {
  instructions: string;
  exam_at: string | null;
  exam_minutes: number;
  max_points: number | null;
  rubric: RubricCriterion[];
  questions: ClassQuestion[];
  files: ClassFile[];
}
export interface ClassGrade {
  id: string;
  points: number | null;
  feedback: string;
  criteria_scores: number[];
  updated_at: string;
}
export interface ClassSubmission extends WorkState {
  author_name?: string;
  content: string;
  answers: string[];
  files: ClassFile[];
  grade: ClassGrade | null;
}
export interface WorkRevision {
  id: string;
  version: number;
  change: string;
  created_at: string;
  snapshot: Pick<ClassSubmission, 'content' | 'answers' | 'files' | 'grade' | 'status'>;
}

export const FILE_TYPES = '.pdf,.txt,.md,.csv,.docx,.xlsx,.pptx,.png,.jpg,.jpeg';
export const ACTIVITY_LABELS: Record<ActivityKind, string> = {
  task: 'Tarea', exercise: 'Ejercicio', quiz: 'Cuestionario', project: 'Proyecto', exam: 'Examen',
};
export const ACTIVITY_STATUS: Record<ActivityStatus, string> = {draft: 'Borrador', published: 'Publicada', closed: 'Cerrada'};
export const WORK_STATUS: Record<WorkStatus, string> = {draft: 'Borrador', submitted: 'Entregada', returned: 'Devuelta'};
