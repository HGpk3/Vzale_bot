const STATUS_LABELS_RU: Record<string, string> = {
  draft: 'Черновик',
  announced: 'Анонсирован',
  registration_open: 'Открыта регистрация',
  running: 'Идет',
  active: 'Активен',
  archived: 'Архив',
  scheduled: 'Запланирован',
  finished: 'Завершен',
  cancelled: 'Отменен',
  canceled: 'Отменен',
  pending: 'Ожидание',
  approved: 'Подтвержден',
  consumed: 'Использован',
  expired: 'Истек',
  open: 'Открыт',
  closed: 'Закрыт',
  replied: 'Отвечено',
  rejected: 'Отклонено',
};

export function statusLabelRu(status: string | null | undefined): string {
  if (!status) return '-';
  return STATUS_LABELS_RU[status.toLowerCase()] ?? status;
}
