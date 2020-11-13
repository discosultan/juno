import React from 'react';
import {
  BrowserRouter as Router,
  Switch,
  Route,
  Link as RouterLink,
} from 'react-router-dom';
import useMediaQuery from '@material-ui/core/useMediaQuery';
import { makeStyles } from '@material-ui/core/styles';
import { createMuiTheme, ThemeProvider } from '@material-ui/core/styles';
import AppBar from '@material-ui/core/AppBar';
import CssBaseline from '@material-ui/core/CssBaseline';
import Link from "@material-ui/core/Link";
import Toolbar from '@material-ui/core/Toolbar';
import Typography from '@material-ui/core/Typography';
import { MuiPickersUtilsProvider } from '@material-ui/pickers';
import DateFnsUtils from '@date-io/date-fns';
import Dashboard from './components/Dashboard';

const useStyles = makeStyles(theme => ({
  appBarItem: {
    marginRight: theme.spacing(2),
  },
  appBar: {
    zIndex: theme.zIndex.drawer + 1,
  },
}));

export default function App() {
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)');
  const classes = useStyles();

  const theme = React.useMemo(
    () =>
      createMuiTheme({
        palette: {
          type: prefersDarkMode ? 'dark' : 'light',
        },
      }),
    [prefersDarkMode],
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline/>
      <MuiPickersUtilsProvider utils={DateFnsUtils}>
        <Router>
          <AppBar className={classes.appBar}>
            <Toolbar>
              <Link component={RouterLink} to="/backtest" className={classes.appBarItem}>
                <Typography color="textPrimary" variant="h6">Backtest</Typography>
              </Link>
              <Link component={RouterLink} to="/optimize" className={classes.appBarItem}>
                <Typography color="textPrimary" variant="h6">Optimize</Typography>
              </Link>
            </Toolbar>
          </AppBar>

          <Switch>
            <Route path="/backtest">
              backtest yo
            </Route>
            <Route path="/">
              <Dashboard />
            </Route>
          </Switch>
        </Router>
      </MuiPickersUtilsProvider>
    </ThemeProvider>
  );
}
