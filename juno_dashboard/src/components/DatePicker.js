import React from 'react';
import DateFnsUtils from '@date-io/date-fns';
import { DatePicker as MuiDatePicker } from '@material-ui/pickers';

/*
 * Beware workarounds involving bugs in material-ui-pickers' design.
 *
 * See https://github.com/mui-org/material-ui-pickers/issues/1358#issuecomment-628015527
 *
 * @material-ui/pickers operate on a Date, but we really want a String.
 * These funky DateUtils let @material-ui/pickers pick dates in the local
 * timezone ... but they ensure outside callers only see ISO8601 Strings.
 */

/**
 * Convert a _local-time_ value to an ISO-8601 Date string.
 *
 * For instance: given 2020-05-13T03:59:50.000Z, if we're in UTC-4,
 * return "2020-05-12".
 *
 * Why? Because material-ui selects dates in local time, not in UTC. If we
 * were to run date.toISOString(), that would convert to UTC and then
 * convert to String; but if we convert to UTC, that changes the date.
 */
function jsDateToLocalISO8601DateString(date) {
  return [
    String(date.getFullYear()),
    String(101 + date.getMonth()).substring(1),
    String(100 + date.getDate()).substring(1),
  ].join('-');
}

function dateStringToLocalDate(s) {
  if (!s) return null;
  return new DateFnsUtils().parse(s, 'yyyy-MM-dd');
}

export default function DatePicker({ label, value, onChange }) {
  const handleChange = React.useCallback(
    (date) => {
      onChange({ target: { value: date ? jsDateToLocalISO8601DateString(date) : null } });
    },
    [onChange],
  );

  return (
    <MuiDatePicker
      variant="inline"
      format="yyyy-MM-dd"
      label={label}
      fullWidth
      disableFuture
      autoOk={true}
      value={dateStringToLocalDate(value)}
      onChange={handleChange}
    />
  );
}
