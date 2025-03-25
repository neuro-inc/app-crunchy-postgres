{{- define "mychart.getSecretValue" -}}

{{- $name := .name }}
{{- $namespace := .namespace }}
{{- $key := .key }}
{{- $ctx := .ctx }}
{{- $value := "" }}

{{- if semverCompare ">=3.2.0" $ctx.Capabilities.HelmVersion.Version }}
  {{- $secret := lookup "v1" "Secret" $namespace $name }}
  {{- if $secret }}
    {{- $data := index $secret.data $key }}
    {{- if $data }}
      {{- $value = $data }}
    {{- else }}
      # INFO: ❌ Key '{{ $key }}' NOT found in secret
    {{- end }}
  {{- else }}
    # INFO: ❌ Secret '{{ $name }}' NOT found in namespace '{{ $namespace }}'
  {{- end }}
{{- else }}
  # INFO: Helm version < 3.2.0 — lookup not supported
{{- end }}

{{- $value }}
{{- end }}


{{- define "mychart.resolveGcsKey" -}}
{{- $ctx := . }}
{{- $gcsSecretValue := "" }}

{{- if kindIs "string" $ctx.Values.gcs.key }}
  {{- $gcsSecretValue = $ctx.Values.gcs.key }}
{{- else if and $ctx.Values.gcs.key.valueFrom.secretKeyRef.name $ctx.Values.gcs.key.valueFrom.secretKeyRef.key }}
  {{- $externalValue := include "mychart.getSecretValue" (dict
      "name" $ctx.Values.gcs.key.valueFrom.secretKeyRef.name
      "namespace" $ctx.Release.Namespace
      "key" $ctx.Values.gcs.key.valueFrom.secretKeyRef.key
      "ctx" $ctx) }}
  {{- $gcsSecretValue = $externalValue }}
{{- else }}
  # DEBUG: Invalid gcs.key format
{{- end }}
{{- $gcsSecretValue }}
{{- end }}

{{- define "mychart.resolveAwsS3Key" -}}
{{- $ctx := . }}
{{- $awsKeyValue := "" }}

{{- if kindIs "string" $ctx.Values.s3.key }}
  {{- $awsKeyValue = $ctx.Values.s3.key }}
{{- else if and $ctx.Values.s3.key.valueFrom.secretKeyRef.name $ctx.Values.s3.key.valueFrom.secretKeyRef.key }}
  {{- $externalValue := include "mychart.getSecretValue" (dict
      "name" $ctx.Values.s3.key.valueFrom.secretKeyRef.name
      "namespace" $ctx.Release.Namespace
      "key" $ctx.Values.s3.key.valueFrom.secretKeyRef.key
      "ctx" $ctx) }}
  {{- $awsKeyValue = $externalValue }}
{{- else }}
  {{- printf "# Invalid gcs.key format" }}
{{- end }}

{{- $awsKeyValue }}
{{- end }}

{{- define "mychart.resolveAwsS3KeySecret" -}}
{{- $ctx := . }}
{{- $awsKeyValueSecret := "" }}

{{- if kindIs "string" $ctx.Values.s3.keySecret }}
  {{- $awsKeyValueSecret = $ctx.Values.s3.keySecret }}
{{- else if and $ctx.Values.s3.keySecret.valueFrom.secretKeyRef.name $ctx.Values.s3.keySecret.valueFrom.secretKeyRef.key }}
  {{- $externalValue := include "mychart.getSecretValue" (dict
      "name" $ctx.Values.s3.keySecret.valueFrom.secretKeyRef.name
      "namespace" $ctx.Release.Namespace
      "key" $ctx.Values.s3.keySecret.valueFrom.secretKeyRef.key
      "ctx" $ctx) }}
  {{- $awsKeyValueSecret = $externalValue }}
{{- else }}
  {{- printf "# Invalid gcs.key format" }}
{{- end }}

{{- $awsKeyValueSecret }}
{{- end }}
