meteorite.IL = 10000;
meteorite.impactStart = 170;
meteorite.coordinates = [-0.54 0.54];
meteorite.holeRadius_IL4 = 0.03;
meteorite.holeRadius_IL5 = 0.09;
meteorite.dustDuration = 18;
meteorite.dustAccumRate = '0 ! 10 ! 10';
Sys6U.agent_operational_mode = 1;
Sys6U.settings_csv = 'HMS_Agent_Settings_User.csv';
Sys6U.test_settings_file = 'Diagnostic_Test_Settings_User.csv';

randomVar = [meteorite.IL];

for t = 1:10 
    meteorite.IL = meteorite.IL + 2;
    randomVar = [randomVar meteorite.IL];
end

myFig = figure;
t = [0:10];
plot(t,randomVar)
xlabel("Time")
ylabel("Random Variable")

timeStr = datestr(now, 'yyyy-mm-dd_HH-MM-SS');
fileName = sprintf('myplot_%s.png', timeStr);

saveas(myFig, fileName)
savefig("myplot.fig")