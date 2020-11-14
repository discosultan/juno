import React, { useState } from 'react';
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';
import Typography from '@material-ui/core/Typography';

export default function History({ gensInfo, history, onChange }) {
  const foundIndex = history.findIndex((item) => item.gensInfo === gensInfo);
  const [indexStr, setIndexStr] = useState(foundIndex === -1 ? '' : `${foundIndex}`);

  function change(indexStr) {
    onChange(history[Number(indexStr)].gensInfo);
    setIndexStr(indexStr);
  }

  return (
    <>
      <Typography variant="h6" gutterBottom>
        View Historical Sessions
      </Typography>
      <TextField
        id="optimize-history"
        label="Optimization History"
        fullWidth
        select
        SelectProps={{
          value: indexStr,
          onChange: (e) => change(e.target.value),
        }}
      >
        {history.map((item, i) => (
          <MenuItem key={i} value={`${i}`}>
            {item.time} ({item.gensInfo.args.strategy})
          </MenuItem>
        ))}
      </TextField>
    </>
  );
}
