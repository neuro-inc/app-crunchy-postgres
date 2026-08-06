{{/* Whether any pgBackRest repository is configured. Empty output means backups are off */}}
{{- define "postgres.backupsConfigured" }}
{{- if or .Values.pgBackRestConfig .Values.multiBackupRepos .Values.s3 .Values.gcs .Values.azure .Values.backupsSize }}
true
{{- end }}
{{- end }}
