// Constraint/constant-speed adapters only. The search is unmodified OMPL control::SST.
#include <ompl/control/SpaceInformation.h>
#include <ompl/control/spaces/RealVectorControlSpace.h>
#include <ompl/control/planners/sst/SST.h>
#include <ompl/control/PathControl.h>
#include <ompl/base/spaces/RealVectorStateSpace.h>
#include <ompl/base/goals/GoalSampleableRegion.h>
#include <ompl/base/objectives/PathLengthOptimizationObjective.h>
#include <ompl/base/PlannerData.h>
#include <ompl/util/RandomNumbers.h>
#include <ompl/config.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <unordered_map>
#include <set>
#include <cmath>
#include <array>
namespace ob=ompl::base;namespace oc=ompl::control;using json=nlohmann::json;
using V=std::array<double,2>;
double length(V p,V q){return std::hypot(p[0]-q[0],p[1]-q[1]);}
double dot(V p,V q){return p[0]*q[0]+p[1]*q[1];}
V sub(V p,V q){return {p[0]-q[0],p[1]-q[1]};}
V lerp(V p,V q,double f){return {p[0]+f*(q[0]-p[0]),p[1]+f*(q[1]-p[1])};}
double segDist(V c,V a,V b){V d=sub(b,a);double den=dot(d,d);return length(c,lerp(a,b,den?std::clamp(dot(sub(c,a),d)/den,0.,1.):0.));}
struct Ship{double ta,tb;V a,b;};
struct Circle{V c;double r;};
struct Model{
 json j;V origin,goal;double speed,horizon,tol,buffer,step,lengthScale,timeScale;std::vector<Ship> ships;std::vector<Circle> circles;
 std::unordered_map<long long,std::vector<int>> bins;long long edges=0,invalid=0;
 long long key(int x,int y)const{return (static_cast<long long>(x)<<32)^static_cast<unsigned int>(y);}
 explicit Model(json input):j(std::move(input)){
  origin=j["start_xy"].get<V>();goal=j["end_xy"].get<V>();speed=j["speed_mps"];horizon=std::min(j["horizon_s"].get<double>(),j.value("search_time_upper_s",j["horizon_s"].get<double>()));tol=j["clearance_tolerance_m"];buffer=j["buffer_m"];step=j["grid_step_m"];
  lengthScale=j.value("state_length_scale_m",speed);timeScale=j.value("state_time_scale_s",1.);
  for(auto&s:j["ships"])ships.push_back({s["ta"],s["tb"],s["a"].get<V>(),s["b"].get<V>()});
  for(auto&b:j["building_circles"]){Circle c{{b[0],b[1]},b[2].get<double>()+tol};int i=circles.size();circles.push_back(c);for(int x=std::floor((c.c[0]-c.r)/step);x<=std::floor((c.c[0]+c.r)/step);x++)for(int y=std::floor((c.c[1]-c.r)/step);y<=std::floor((c.c[1]+c.r)/step);y++)bins[key(x,y)].push_back(i);}
 }
 V xy(const ob::State*s)const{const double*v=s->as<ob::RealVectorStateSpace::StateType>()->values;return {origin[0]+lengthScale*v[0],origin[1]+lengthScale*v[1]};}
 double time(const ob::State*s)const{return timeScale*s->as<ob::RealVectorStateSpace::StateType>()->values[2];}
 bool valid(V a,V b,double ta,double tb){
  ++edges;if(ta<0||tb>horizon||tb<ta){++invalid;return false;}
  // A necessary model condition, not a search algorithm: even a straight flight
  // at the unchanged speed must fit in the remaining observation query time.
  if(j.contains("search_time_upper_s")&&tb+length(b,goal)/speed>horizon+1e-9){++invalid;return false;}
  std::set<int> ids;for(int x=std::floor(std::min(a[0],b[0])/step);x<=std::floor(std::max(a[0],b[0])/step);x++)for(int y=std::floor(std::min(a[1],b[1])/step);y<=std::floor(std::max(a[1],b[1])/step);y++){auto it=bins.find(key(x,y));if(it!=bins.end())ids.insert(it->second.begin(),it->second.end());}
  for(int i:ids)if(segDist(circles[i].c,a,b)<circles[i].r){++invalid;return false;}
  for(const auto&s:ships){double lo=std::max(ta,s.ta),hi=std::min(tb,s.tb);if(lo>hi)continue;auto boat=[&](double t){return s.tb==s.ta?s.a:lerp(s.a,s.b,(t-s.ta)/(s.tb-s.ta));};auto uav=[&](double t){return tb==ta?a:lerp(a,b,(t-ta)/(tb-ta));};V r0=sub(uav(lo),boat(lo)),r1=sub(uav(hi),boat(hi));if(segDist({0,0},r0,r1)<buffer+tol){++invalid;return false;}}
  return true;
 }
};
struct GoalXY:ob::GoalSampleableRegion{
 Model&m;double numericalTolerance;
 GoalXY(const ob::SpaceInformationPtr&si,Model&model,double epsilon):ob::GoalSampleableRegion(si),m(model),numericalTolerance(epsilon){setThreshold(epsilon);}
 double distanceGoal(const ob::State*s)const override{return length(m.xy(s),m.goal);}
 bool isSatisfied(const ob::State*s,double*distance)const override{double d=distanceGoal(s);if(distance)*distance=d;if(d>=numericalTolerance)return false;return !m.j.value("terminal_connector_enabled",false)||m.valid(m.xy(s),m.goal,m.time(s),m.time(s)+d/m.speed);}
 void sampleGoal(ob::State*s)const override{auto*v=s->as<ob::RealVectorStateSpace::StateType>()->values;v[0]=(m.goal[0]-m.origin[0])/m.lengthScale;v[1]=(m.goal[1]-m.origin[1])/m.lengthScale;v[2]=length(m.origin,m.goal)/m.speed/m.timeScale;}
 unsigned int maxSampleCount()const override{return 1;}
};
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("sst_probe input.json output.json");json j;std::ifstream(argv[1])>>j;Model m(j);ompl::RNG::setSeed(j.value("seed",42));
 auto space=std::make_shared<ob::RealVectorStateSpace>(3);ob::RealVectorBounds bounds(3);for(int i=0;i<2;i++){bounds.setLow(i,(j["bounds"][i*2].get<double>()-m.origin[i])/m.lengthScale);bounds.setHigh(i,(j["bounds"][i*2+1].get<double>()-m.origin[i])/m.lengthScale);}bounds.setLow(2,0);bounds.setHigh(2,m.horizon/m.timeScale);space->setBounds(bounds);
 auto controls=std::make_shared<oc::RealVectorControlSpace>(space,1);ob::RealVectorBounds cb(1);double angle=j.value("heading_limit_rad",3.141592653589793);cb.setLow(-angle);cb.setHigh(angle);controls->setBounds(cb);
 auto si=std::make_shared<oc::SpaceInformation>(space,controls);si->setPropagationStepSize(j.value("propagation_step_s",.1));si->setMinMaxControlDuration(1,j.value("maximum_control_steps",50));
 si->setStateValidityChecker([&](const ob::State*s){return si->satisfiesBounds(s)&&m.valid(m.xy(s),m.xy(s),m.time(s),m.time(s));});
 si->setStatePropagator([&](const ob::State*s,const oc::Control*c,double duration,ob::State*out){
  const double*v=s->as<ob::RealVectorStateSpace::StateType>()->values;double theta=c->as<oc::RealVectorControlSpace::ControlType>()->values[0];V p=m.xy(s);double t=m.time(s);auto*w=out->as<ob::RealVectorStateSpace::StateType>()->values;w[0]=v[0]+duration*m.speed/m.lengthScale*std::cos(theta);w[1]=v[1]+duration*m.speed/m.lengthScale*std::sin(theta);w[2]=v[2]+duration/m.timeScale;
  if(!m.valid(p,m.xy(out),t,m.time(out)))w[2]=m.horizon/m.timeScale+1; // Invalid state, never a detour or a changed ship.
 });
 ob::ScopedState<> start(space);start[0]=0;start[1]=0;start[2]=0;
 auto pdef=std::make_shared<ob::ProblemDefinition>(si);pdef->addStartState(start);pdef->setGoal(std::make_shared<GoalXY>(si,m,j.value("goal_numerical_tolerance_m",1e-6)));
 // Native state coordinates (x/v,y/v,t) give a path length proportional to physical
 // length for constant-speed segments. No custom route objective or postprocessor.
 pdef->setOptimizationObjective(std::make_shared<ob::PathLengthOptimizationObjective>(si));
 auto planner=std::make_shared<oc::SST>(si);if(j.contains("selection_radius"))planner->setSelectionRadius(j["selection_radius"]);if(j.contains("pruning_radius"))planner->setPruningRadius(j["pruning_radius"]);if(j.contains("goal_bias"))planner->setGoalBias(j["goal_bias"]);planner->setProblemDefinition(pdef);planner->setup();auto status=planner->ob::Planner::solve(j.value("solve_seconds",10.));
 json result={{"library","OMPL"},{"version",OMPL_VERSION},{"planner","ompl::control::SST"},{"status",status.asString()},{"exact",status==ob::PlannerStatus::EXACT_SOLUTION},{"approximate",status==ob::PlannerStatus::APPROXIMATE_SOLUTION},{"seed",j.value("seed",42)},{"goal_numerical_tolerance_m",j.value("goal_numerical_tolerance_m",1e-6)},{"edges_checked",m.edges},{"invalid_edges",m.invalid},{"states",json::array()},{"controls",json::array()}};
 if(pdef->hasSolution()){
  auto path=std::dynamic_pointer_cast<oc::PathControl>(pdef->getSolutionPath());double distance=0;
  for(unsigned i=0;i<path->getStateCount();i++){auto*s=path->getState(i);V xy=m.xy(s);result["states"].push_back({{"xy",xy},{"t",m.time(s)}});if(i)distance+=length(xy,m.xy(path->getState(i-1)));}
  for(unsigned i=0;i<path->getControlCount();i++)result["controls"].push_back({{"heading_rad",path->getControl(i)->as<oc::RealVectorControlSpace::ControlType>()->values[0]},{"duration_s",path->getControlDuration(i)}});
  result["distance_m"]=distance;result["endpoint_error_m"]=length(m.xy(path->getState(path->getStateCount()-1)),m.goal);result["duration_s"]=m.time(path->getState(path->getStateCount()-1));
  if(j.value("terminal_connector_enabled",false)&&status==ob::PlannerStatus::EXACT_SOLUTION){auto*last=path->getState(path->getStateCount()-1);double t=m.time(last),dt=length(m.xy(last),m.goal)/m.speed;result["terminal_connection"]={{"from_xy",m.xy(last)},{"to_xy",m.goal},{"departure_s",t},{"arrival_s",t+dt},{"speed_mps",m.speed},{"distance_m",length(m.xy(last),m.goal)},{"valid",m.valid(m.xy(last),m.goal,t,t+dt)}};}
 }
 std::ofstream(argv[2])<<result.dump(2);std::cout<<result["status"]<<" endpoint error "<<result.value("endpoint_error_m",-1.)<<"m\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}}
