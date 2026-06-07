import { useAnalyzeResume } from "@/api/hooks";
import type { ResumeAnalysisData, ResumeAnalysisMeta } from "@/api/types";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
    AlertCircle,
    CheckCircle2,
    FileText,
    Loader2,
    Shield,
    Sparkles,
    Target,
    Upload,
    XCircle,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";

type InputMode = "file" | "text";
type TargetGrade = "" | "junior" | "middle" | "senior";

const ACCEPTED_FORMATS = ".pdf,.docx";
const MAX_FILE_SIZE_MB = 5;

export function ResumeAnalyzer() {
  const [mode, setMode] = useState<InputMode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [targetGrade, setTargetGrade] = useState<TargetGrade>("");
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const mutation = useAnalyzeResume();

  const canSubmit =
    !mutation.isPending &&
    ((mode === "file" && file !== null) ||
      (mode === "text" && text.trim().length > 0));

  const handleFileChange = useCallback(
    (f: File | null) => {
      if (!f) return;
      if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        alert(`Файл слишком большой. Максимум ${MAX_FILE_SIZE_MB} МБ.`);
        return;
      }
      const ext = f.name.toLowerCase();
      if (!ext.endsWith(".pdf") && !ext.endsWith(".docx")) {
        alert("Поддерживаются только PDF и DOCX файлы.");
        return;
      }
      setFile(f);
    },
    [],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const f = e.dataTransfer.files[0];
      handleFileChange(f ?? null);
    },
    [handleFileChange],
  );

  const handleSubmit = () => {
    if (!canSubmit) return;
    mutation.mutate({
      file: mode === "file" ? file ?? undefined : undefined,
      resumeText: mode === "text" ? text : undefined,
      targetGrade: targetGrade || undefined,
    });
  };

  const result = mutation.data;

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            <h1 className="text-lg font-bold">Анализатор резюме</h1>
            <span className="text-sm text-muted-foreground hidden sm:inline">
              — Оценка соответствия рынку Frontend
            </span>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 space-y-6 max-w-4xl">
        {/* Privacy notice */}
        <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-4">
          <Shield className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
          <div className="text-sm text-blue-800 dark:text-blue-300">
            <p className="font-medium mb-1">Конфиденциальность</p>
            <p>
              Ваше резюме <strong>обезличивается</strong> перед анализом: имя, телефон, email,
              адрес и другие персональные данные автоматически удаляются.
              Резюме <strong>не сохраняется</strong> на сервере.
              Анализируется только профессиональное содержание — навыки, опыт и стек технологий.
            </p>
          </div>
        </div>

        {/* Input card */}
        <Card>
          <CardHeader>
            <CardTitle>Загрузите резюме</CardTitle>
            <CardDescription>
              Выберите способ ввода: загрузите файл (PDF/DOCX) или вставьте текст
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Mode tabs */}
            <div className="flex gap-1 p-1 bg-muted rounded-lg w-fit">
              <button
                onClick={() => setMode("file")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  mode === "file"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Upload className="h-4 w-4" />
                Загрузить файл
              </button>
              <button
                onClick={() => setMode("text")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  mode === "text"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <FileText className="h-4 w-4" />
                Вставить текст
              </button>
            </div>

            {/* File upload */}
            {mode === "file" && (
              <div
                className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                  dragActive
                    ? "border-primary bg-primary/5"
                    : file
                      ? "border-green-400 bg-green-50 dark:bg-green-950/20"
                      : "border-muted-foreground/30 hover:border-primary/50"
                }`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_FORMATS}
                  className="hidden"
                  onChange={(e) =>
                    handleFileChange(e.target.files?.[0] ?? null)
                  }
                />
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <CheckCircle2 className="h-8 w-8 text-green-500" />
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(0)} КБ
                    </p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                      }}
                      className="text-xs text-destructive hover:underline mt-1"
                    >
                      Удалить файл
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Upload className="h-8 w-8 text-muted-foreground/60" />
                    <p className="text-sm text-muted-foreground">
                      Перетащите файл сюда или{" "}
                      <span className="text-primary underline cursor-pointer">
                        выберите
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground/70">
                      PDF или DOCX, до {MAX_FILE_SIZE_MB} МБ
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Text input */}
            {mode === "text" && (
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Вставьте текст резюме..."
                className="w-full h-48 p-3 border rounded-lg bg-background text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            )}

            {/* Target grade selector */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-muted-foreground">
                Целевой грейд:
              </label>
              <select
                value={targetGrade}
                onChange={(e) =>
                  setTargetGrade(e.target.value as TargetGrade)
                }
                className="border rounded-md px-3 py-1.5 text-sm bg-background"
              >
                <option value="">Все грейды</option>
                <option value="junior">Junior</option>
                <option value="middle">Middle</option>
                <option value="senior">Senior</option>
              </select>
            </div>

            {/* Submit button */}
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="w-full sm:w-auto px-6 py-2.5 bg-primary text-primary-foreground rounded-lg font-medium text-sm transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Анализируем...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Анализировать
                </>
              )}
            </button>

            {/* Error */}
            {mutation.isError && (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/5 p-3">
                <AlertCircle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
                <p className="text-sm text-destructive">
                  {mutation.error?.message || "Произошла ошибка"}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Loading skeleton */}
        {mutation.isPending && (
          <Card>
            <CardContent className="py-6 space-y-4">
              <Skeleton className="h-8 w-1/3" />
              <Skeleton className="h-4 w-2/3" />
              <div className="grid grid-cols-2 gap-4">
                <Skeleton className="h-24" />
                <Skeleton className="h-24" />
              </div>
              <Skeleton className="h-32" />
            </CardContent>
          </Card>
        )}

        {/* Result */}
        {result && !mutation.isPending && (
          <AnalysisResult data={result.data} meta={result.meta} />
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Analysis result display
// ---------------------------------------------------------------------------

function AnalysisResult({
  data,
  meta,
}: {
  data: ResumeAnalysisData;
  meta: ResumeAnalysisMeta;
}) {
  const scoreColor =
    data.market_fit_score >= 70
      ? "text-green-600"
      : data.market_fit_score >= 40
        ? "text-yellow-600"
        : "text-red-600";

  const scoreBg =
    data.market_fit_score >= 70
      ? "bg-green-100 dark:bg-green-950/30"
      : data.market_fit_score >= 40
        ? "bg-yellow-100 dark:bg-yellow-950/30"
        : "bg-red-100 dark:bg-red-950/30";

  return (
    <div className="space-y-4">
      {/* LLM warning if rule-based only */}
      {data.llm_error && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-300 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-950/20 p-3">
          <AlertCircle className="h-4 w-4 text-yellow-600 mt-0.5 shrink-0" />
          <p className="text-sm text-yellow-800 dark:text-yellow-300">
            {data.llm_error}
          </p>
        </div>
      )}

      {/* Score + Grade + Salary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Score */}
        <Card>
          <CardContent className="pt-6 text-center">
            <div
              className={`inline-flex items-center justify-center w-20 h-20 rounded-full ${scoreBg} mb-2`}
            >
              <span className={`text-3xl font-bold ${scoreColor}`}>
                {data.market_fit_score}
              </span>
            </div>
            <p className="text-sm font-medium">Соответствие рынку</p>
            <p className="text-xs text-muted-foreground">из 100</p>
          </CardContent>
        </Card>

        {/* Grade */}
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="text-2xl font-bold mb-2">
              {data.estimated_grade
                ? data.estimated_grade.charAt(0).toUpperCase() +
                  data.estimated_grade.slice(1)
                : "—"}
            </div>
            <p className="text-sm font-medium">Предполагаемый грейд</p>
            {data.salary_range && (
              <p className="text-xs text-muted-foreground mt-1">
                {data.salary_range.from
                  ? `${(data.salary_range.from / 1000).toFixed(0)}k`
                  : "—"}
                {" – "}
                {data.salary_range.to
                  ? `${(data.salary_range.to / 1000).toFixed(0)}k ₽`
                  : "—"}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Filters */}
        <Card>
          <CardContent className="pt-6 text-center">
            <div className="flex items-center justify-center mb-2">
              {data.passes_keyword_filters ? (
                <CheckCircle2 className="h-10 w-10 text-green-500" />
              ) : (
                <XCircle className="h-10 w-10 text-red-500" />
              )}
            </div>
            <p className="text-sm font-medium">
              {data.passes_keyword_filters
                ? "Пройдёт фильтры"
                : "Не пройдёт фильтры"}
            </p>
            <p className="text-xs text-muted-foreground">
              по ключевым словам ({(data.skill_match_ratio * 100).toFixed(0)}%
              покрытие)
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Skills */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Навыки</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Matched */}
          {data.matched_skills.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                ✅ Совпадают с рынком ({data.matched_skills.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {data.matched_skills.map((s) => (
                  <span
                    key={s}
                    className="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Missing */}
          {data.missing_in_demand_skills.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                ❌ Отсутствуют из востребованных (
                {data.missing_in_demand_skills.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {data.missing_in_demand_skills.map((s) => (
                  <span
                    key={s}
                    className="px-2 py-0.5 text-xs rounded-full bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* All resume skills */}
          {data.resume_skills.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                📋 Все найденные навыки ({data.resume_skills.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {data.resume_skills.map((s) => (
                  <span
                    key={s}
                    className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Strengths & Weaknesses */}
      {(data.strengths.length > 0 || data.weaknesses.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {data.strengths.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-green-700 dark:text-green-400">
                  💪 Сильные стороны
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {data.strengths.map((s, i) => (
                    <li
                      key={i}
                      className="text-sm flex items-start gap-1.5"
                    >
                      <span className="text-green-500 mt-0.5">•</span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
          {data.weaknesses.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-red-700 dark:text-red-400">
                  ⚠️ Слабые стороны
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {data.weaknesses.map((s, i) => (
                    <li
                      key={i}
                      className="text-sm flex items-start gap-1.5"
                    >
                      <span className="text-red-500 mt-0.5">•</span>
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">💡 Рекомендации</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {data.recommendations.map((r, i) => (
                <li key={i} className="text-sm flex items-start gap-2">
                  <span className="bg-primary text-primary-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <span>{r}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Meta */}
      <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground/70 px-1">
        {meta.model && <span>Модель: {meta.model}</span>}
        {meta.llm_enhanced && <span>✨ Расширен ИИ</span>}
        {meta.pii_entities_removed != null && meta.pii_entities_removed > 0 && (
          <span>🔒 Удалено PII: {meta.pii_entities_removed}</span>
        )}
        {data.market_sample_size > 0 && (
          <span>Выборка: {data.market_sample_size} вакансий</span>
        )}
        {meta.analyzed_at && (
          <span>
            Анализ: {new Date(meta.analyzed_at).toLocaleString("ru-RU")}
          </span>
        )}
      </div>
    </div>
  );
}
