import pytest
from parsers.javascript_parser import JavaScriptParser
from parser import CodeParser


def test_parse_javascript_classes_and_commonjs():
    parser = JavaScriptParser()
    code = b"""
const express = require('express');
const { calculateTax } = require('./tax');

class OrderService extends BaseService {
  constructor(db) {
    super(db);
    this.db = db;
  }

  processOrder(order) {
    const tax = calculateTax(order.amount);
    return this.db.save({ ...order, tax });
  }
}

class OrderController {
  constructor(service) {
    this.service = service;
  }

  getOrder(req, res) {
    return this.service.processOrder(req.body);
  }
}

module.exports = { OrderService, OrderController };
"""
    res = parser.parse_file("services/order.js", code)

    # Check file language
    assert res["files"][0]["language"] == "javascript"

    # Check classes
    classes = {c["name"]: c["category"] for c in res["classes"]}
    assert classes["OrderService"] == "service"
    assert classes["OrderController"] == "controller"

    # Check inheritance / implements
    implements = [imp["interface_name"] for imp in res["implements"]]
    assert "BaseService" in implements

    # Check functions / methods
    func_names = {f["name"]: f["category"] for f in res["functions"]}
    assert func_names["processOrder"] == "method"
    assert func_names["getOrder"] == "method"

    # Check containment
    contains_edges = [(c["class_id"], c["function_id"]) for c in res["contains"]]
    assert any("OrderService" in c[0] and "processOrder" in c[1] for c in contains_edges)
    assert any("OrderController" in c[0] and "getOrder" in c[1] for c in contains_edges)

    # Check CommonJS imports
    imported_modules = [imp["imported_module"] for imp in res["imports"]]
    assert "express" in imported_modules
    assert "./tax" in imported_modules

    # Check calls
    calls = [(call["caller_id"], call["callee_name"]) for call in res["calls"]]
    assert any("processOrder" in call[0] and call[1] == "calculateTax" for call in calls)
    assert any("getOrder" in call[0] and call[1] == "processOrder" for call in calls)


def test_parse_react_jsx_components_and_hooks():
    parser = JavaScriptParser()
    code = b"""
import React, { useState, useEffect } from 'react';
import { Button } from './Button';

export const Header = ({ title }) => {
  return (
    <header className="header">
      <Logo />
      <Navbar.Brand title={title} />
      <Button variant="primary" />
    </header>
  );
};

export function UserCard({ user }) {
  return (
    <div className="user-card">
      <Avatar src={user.avatar} />
      <span>{user.name}</span>
    </div>
  );
}

export function useUserProfile(userId) {
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    fetchUserData(userId).then(setProfile);
  }, [userId]);

  return profile;
}
"""
    res = parser.parse_file("components/Header.jsx", code)

    # Check file language
    assert res["files"][0]["language"] == "jsx"

    # Check functions and categories
    func_categories = {f["name"]: f["category"] for f in res["functions"]}
    assert func_categories["Header"] == "component"
    assert func_categories["UserCard"] == "component"
    assert func_categories["useUserProfile"] == "hook"

    # Check ES imports
    imported_modules = [imp["imported_module"] for imp in res["imports"]]
    assert any("react" in imp for imp in imported_modules)
    assert any("./Button" in imp for imp in imported_modules)

    # Check JSX renders
    renders = [(r["parent_func_id"], r["rendered_component_name"]) for r in res["renders"]]
    assert any("Header" in r[0] and r[1] == "Logo" for r in renders)
    assert any("Header" in r[0] and r[1] == "Navbar.Brand" for r in renders)
    assert any("Header" in r[0] and r[1] == "Button" for r in renders)
    assert any("UserCard" in r[0] and r[1] == "Avatar" for r in renders)

    # Check hook calls
    calls = [(c["caller_id"], c["callee_name"]) for c in res["calls"]]
    assert any("useUserProfile" in c[0] and c[1] == "useState" for c in calls)
    assert any("useUserProfile" in c[0] and c[1] == "useEffect" for c in calls)
    assert any("useUserProfile" in c[0] and c[1] == "fetchUserData" for c in calls)


def test_code_parser_routing_for_js_and_jsx(tmp_path):
    parser = CodeParser()

    js_file = tmp_path / "app.js"
    js_file.write_text("function add(a, b) { return a + b; }", encoding="utf-8")

    jsx_file = tmp_path / "App.jsx"
    jsx_file.write_text("export function App() { return <div><Header /></div>; }", encoding="utf-8")

    res_js = parser.parse_file(str(js_file))
    assert res_js["files"][0]["language"] == "javascript"
    assert res_js["functions"][0]["name"] == "add"

    res_jsx = parser.parse_file(str(jsx_file))
    assert res_jsx["files"][0]["language"] == "jsx"
    assert res_jsx["functions"][0]["name"] == "App"
    assert res_jsx["functions"][0]["category"] == "component"
    assert res_jsx["renders"][0]["rendered_component_name"] == "Header"
