import React from 'react';
import Drawer from '@material-ui/core/Drawer';
import Toolbar from '@material-ui/core/Toolbar';
import { makeStyles } from '@material-ui/core/styles';

const drawerWidth = '20%';
const useStyles = makeStyles((_theme) => ({
  drawer: {
    width: drawerWidth,
  },
  main: {
    marginLeft: drawerWidth,
  },
}));

export default function SplitPane({ left, right }) {
  const classes = useStyles();

  return (
    <>
      <Drawer
        variant="permanent"
        anchor="left"
        className={classes.drawer}
        classes={{ paper: classes.drawer }}
      >
        {/* Dummy toolbar to add toolbar's worth of space to the top. Otherwise the
                component will run under app bar. Same for the main section below. */}
        <Toolbar variant="dense" />
        {left}
      </Drawer>
      <main className={classes.main}>
        <Toolbar variant="dense" />
        {right}
      </main>
    </>
  );
}
