% Synthetic motion example for testing the Grasshopper/MATLAB connection.
% Copy this file to a working folder before applying a transfer.
% These are simple top-level inputs; the transfer backend edits their values.
v0 = 0;
a = 1;
t_final = 10;
dt = 1;

% MATLAB must execute these expressions to calculate the output arrays.
t = 0:dt:t_final;
v = v0 + a .* t;
s = v0 .* t + 0.5 .* a .* t.^2;
final_displacement = s(end);
fprintf('Calculated %d samples; final displacement = %.6g\n', numel(t), final_displacement);
