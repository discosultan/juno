import React from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import TextareaAutosize from '@material-ui/core/TextareaAutosize';
import TextField from '@material-ui/core/TextField';
import { makeStyles } from '@material-ui/core/styles';

const useStyles = makeStyles((_theme) => ({
  textarea: {
    resize: 'vertical',
    width: '100%',
  },
  label: {
    display: 'block',
  },
}));

export default function DynamicParams({
  label,
  options,
  value,
  onChange,
  paramsValue,
  paramsOnChange,
}) {
  const classes = useStyles();
  const selectId = label;
  const paramsId = `${label}Params`;

  return (
    <>
      <TextField id={selectId} label={label} fullWidth select value={value} onChange={onChange}>
        {options.map((option) => (
          <MenuItem key={option} value={option}>
            {option}
          </MenuItem>
        ))}
      </TextField>
      <label
        className={classes.label + ' MuiFormLabel-root MuiInputLabel-shrink'}
        htmlFor={paramsId}
      >
        {label} Parameters
      </label>
      <TextareaAutosize
        id={paramsId}
        className={classes.textarea}
        aria-label={`${label} parameters`}
        rowsMin={3}
        value={paramsValue}
        onChange={paramsOnChange}
      />
    </>
  );
}
