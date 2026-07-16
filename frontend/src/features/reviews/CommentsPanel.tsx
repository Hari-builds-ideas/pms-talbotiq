import * as React from "react";
import { MessageSquare, Pencil, Reply, Trash2, X } from "lucide-react";
import { Panel } from "@/components/Panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LinesSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/ErrorState";
import { PersonName } from "@/components/PersonName";
import { useReviewComments, useReviewCommentMutations } from "./useReviews";
import { threadComments } from "@/lib/reviewComments";
import { useAuth } from "@/lib/auth/AuthContext";
import { humanize } from "@/lib/enums";
import { formatDateTime } from "@/lib/format";
import { notifyError, notifySuccess } from "@/lib/toast";
import type { ReviewComment } from "@/lib/types";

const SECTIONS = ["SUMMARY", "STRENGTHS", "DEVELOPMENT", "GOALS", "RECOMMENDATIONS"] as const;

/**
 * Comments on a review (BUILD_7 Feature A). Lists one-level threads, lets anyone
 * who can see the review add a comment (optionally tagged to a section) or reply,
 * and lets an author edit/delete their own. Visibility + permission are enforced
 * server-side; the UI only reflects own-vs-others.
 */
export function CommentsPanel({ reviewId }: { reviewId: string }) {
  const comments = useReviewComments(reviewId);
  const m = useReviewCommentMutations(reviewId);
  const threads = threadComments(comments.data ?? []);

  return (
    <Panel title="Comments" icon={MessageSquare}>
      {comments.isLoading ? (
        <LinesSkeleton lines={3} />
      ) : comments.isError ? (
        <ErrorState error={comments.error} onRetry={() => comments.refetch()} compact />
      ) : (
        <div className="space-y-4">
          {threads.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No comments yet. Start the discussion below.
            </p>
          ) : (
            <ul className="space-y-4">
              {threads.map((t) => (
                <li key={t.comment.id} className="space-y-2">
                  <CommentItem comment={t.comment} mutations={m} />
                  {t.replies.length > 0 && (
                    <ul className="space-y-2 border-l border-border pl-3">
                      {t.replies.map((r) => (
                        <li key={r.id}>
                          <CommentItem comment={r} mutations={m} isReply />
                        </li>
                      ))}
                    </ul>
                  )}
                  <ReplyAffordance parentId={t.comment.id} mutations={m} />
                </li>
              ))}
            </ul>
          )}

          <div className="border-t border-border pt-3">
            <NewCommentForm mutations={m} />
          </div>
        </div>
      )}
    </Panel>
  );
}

type Mutations = ReturnType<typeof useReviewCommentMutations>;

function CommentItem({
  comment,
  mutations,
  isReply = false,
}: {
  comment: ReviewComment;
  mutations: Mutations;
  isReply?: boolean;
}) {
  const { me } = useAuth();
  const mine = me?.id === comment.author;
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(comment.body);

  async function saveEdit() {
    if (!draft.trim()) return;
    try {
      await mutations.edit.mutateAsync({ id: comment.id, body: draft.trim() });
      notifySuccess("Comment updated");
      setEditing(false);
    } catch (err) {
      notifyError(err);
    }
  }

  async function remove() {
    try {
      await mutations.remove.mutateAsync(comment.id);
      notifySuccess("Comment deleted");
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">
          <PersonName id={comment.author} name={comment.author_name} />
        </span>
        {!isReply && comment.section && (
          <Badge variant="muted">{humanize(comment.section)}</Badge>
        )}
        <span className="text-2xs text-muted-foreground">{formatDateTime(comment.created_at)}</span>
        {comment.edited_at && <span className="text-2xs text-muted-foreground">(edited)</span>}
      </div>
      {editing ? (
        <div className="mt-1.5 space-y-2">
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} className="min-h-16" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setDraft(comment.body); }}>
              Cancel
            </Button>
            <Button size="sm" onClick={saveEdit} loading={mutations.edit.isPending} disabled={!draft.trim()}>
              Save
            </Button>
          </div>
        </div>
      ) : (
        <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-muted-foreground">{comment.body}</p>
      )}
      {mine && !editing && (
        <div className="mt-1 flex gap-1">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-2xs" onClick={() => setEditing(true)}>
            <Pencil className="h-3 w-3" /> Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-2xs text-danger focus:text-danger"
            onClick={remove}
            loading={mutations.remove.isPending}
          >
            <Trash2 className="h-3 w-3" /> Delete
          </Button>
        </div>
      )}
    </div>
  );
}

function ReplyAffordance({ parentId, mutations }: { parentId: string; mutations: Mutations }) {
  const [open, setOpen] = React.useState(false);
  const [body, setBody] = React.useState("");

  async function submit() {
    if (!body.trim()) return;
    try {
      await mutations.create.mutateAsync({ body: body.trim(), parent: parentId });
      setBody("");
      setOpen(false);
    } catch (err) {
      notifyError(err);
    }
  }

  if (!open) {
    return (
      <Button variant="ghost" size="sm" className="h-7 px-2 text-2xs" onClick={() => setOpen(true)}>
        <Reply className="h-3 w-3" /> Reply
      </Button>
    );
  }
  return (
    <div className="space-y-2 border-l border-border pl-3">
      <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a reply…" className="min-h-16" />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={() => { setOpen(false); setBody(""); }}>
          <X className="h-3 w-3" /> Cancel
        </Button>
        <Button size="sm" onClick={submit} loading={mutations.create.isPending} disabled={!body.trim()}>
          Reply
        </Button>
      </div>
    </div>
  );
}

function NewCommentForm({ mutations }: { mutations: Mutations }) {
  const [body, setBody] = React.useState("");
  const [section, setSection] = React.useState<string>("general");

  async function submit() {
    if (!body.trim()) return;
    try {
      await mutations.create.mutateAsync({
        body: body.trim(),
        section: section === "general" ? null : section,
      });
      setBody("");
      setSection("general");
      notifySuccess("Comment added");
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <div className="space-y-2">
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Add a comment…"
        className="min-h-16"
      />
      <div className="flex items-center justify-between gap-2">
        <Select value={section} onValueChange={setSection}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="general">General comment</SelectItem>
            {SECTIONS.map((s) => (
              <SelectItem key={s} value={s}>{humanize(s)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" onClick={submit} loading={mutations.create.isPending} disabled={!body.trim()}>
          Comment
        </Button>
      </div>
    </div>
  );
}
